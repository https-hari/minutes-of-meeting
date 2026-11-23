"""Retrieval eval: which search finds the right transcript chunk?

32 questions over 4 meetings (76 chunks). Each question has exactly one gold
chunk (a turn containing the gold text). Questions are of three kinds:
  paraphrase - different words from the transcript ("cloud bill" vs "AWS cost")
  exact      - hinge on a token: JIRA-482, 1.22, 18 lakh, 140
  direct     - mostly the same words

Metrics per mode (searching across ALL meetings, as the agent does):
  Recall@k - share of questions whose gold chunk is in the top k
  MRR      - mean of 1/rank of the gold chunk (0 if not in the top 10)

    python eval/run_retrieval_eval.py            # real MiniLM + cross-encoder
    python eval/run_retrieval_eval.py --fake     # plumbing check, no model downloads
"""
import argparse
import csv
import statistics
import time

from common import EVAL_USER, ROOT, load, reset_and_load_chunks, update_readme, use_eval_database

MODES = ["vector", "keyword", "hybrid", "hybrid_rerank"]
KS = [1, 3, 5]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fake", action="store_true", help="fake embedder/re-ranker (tests the harness only)")
    args = ap.parse_args()

    print("Eval database:", use_eval_database().split("@")[-1])
    from app.db.connection import SessionLocal
    from app.retrieval import Retriever

    if args.fake:
        import sys
        sys.path.insert(0, str(ROOT.parent / "tests"))
        from fakes import FakeEmbedder, FakeReranker
        embedder, reranker = FakeEmbedder(), FakeReranker()
    else:
        from app.agents.embedding_agent import EmbeddingAgent
        from app.retrieval import CrossEncoderReranker
        embedder, reranker = EmbeddingAgent(), CrossEncoderReranker()

    n = reset_and_load_chunks(embedder)
    print(f"Loaded {n} chunks from {len(load('meetings.json'))} meetings")
    retriever = Retriever(embedder, reranker)
    questions = load("questions.json")
    db = SessionLocal()

    retriever.search(db, "warm up", k=5, mode="hybrid_rerank", user_id=EVAL_USER)   # load models before timing

    rows, per_q = [], []
    for mode in MODES:
        ranks, times = [], []
        for q in questions:
            t0 = time.perf_counter()
            hits = retriever.search(db, q["q"], k=10, mode=mode, user_id=EVAL_USER)
            times.append(time.perf_counter() - t0)
            gold = q["gold"].lower()
            rank = next((i for i, h in enumerate(hits, 1) if gold in h.text.lower()), None)
            ranks.append(rank)
            per_q.append({"mode": mode, "type": q["type"], "question": q["q"], "rank": rank or ""})
        row = {"mode": mode}
        for k in KS:
            row[f"recall@{k}"] = sum(1 for r in ranks if r and r <= k) / len(ranks)
        row["mrr"] = sum(1 / r for r in ranks if r) / len(ranks)
        row["ms_per_query"] = 1000 * statistics.mean(times)
        for t in ("paraphrase", "exact", "direct"):
            sel = [r for r, q in zip(ranks, questions) if q["type"] == t]
            row[f"recall@3_{t}"] = sum(1 for r in sel if r and r <= 3) / len(sel)
        rows.append(row)
        print(f"{mode:<14} R@1={row['recall@1']:.2f} R@3={row['recall@3']:.2f} "
              f"R@5={row['recall@5']:.2f} MRR={row['mrr']:.3f} {row['ms_per_query']:.0f} ms")
    db.close()

    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    suffix = "_fake" if args.fake else ""
    with open(out / f"retrieval{suffix}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(per_q[0]))
        w.writeheader()
        w.writerows(per_q)
    table = ["| Search | Recall@1 | Recall@3 | Recall@5 | MRR | R@3 paraphrase | R@3 exact-token | ms/query |",
             "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        table.append(f"| {r['mode']} | {r['recall@1']:.0%} | {r['recall@3']:.0%} | {r['recall@5']:.0%} | "
                     f"{r['mrr']:.2f} | {r['recall@3_paraphrase']:.0%} | {r['recall@3_exact']:.0%} | "
                     f"{r['ms_per_query']:.0f} |")
    note = "> FAKE RUN: harness check only.\n\n" if args.fake else ""
    (out / f"retrieval{suffix}.md").write_text(
        note + f"{len(questions)} questions, {n} chunks, 4 meetings.\n\n" + "\n".join(table) + "\n")
    if not args.fake:
        update_readme("RETRIEVAL_RESULTS", "\n".join(table))
    print("\n" + "\n".join(table))


if __name__ == "__main__":
    main()
