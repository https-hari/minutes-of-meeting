"""Agent eval: does the agent pick sensible tools and answer correctly?

Loads the 4 eval meetings through the FULL pipeline (LLM extraction of action
items and decisions), then asks 11 questions. A case passes when:
  tool  - at least one of the expected tools was called
  answer- every group in answer_has has at least one phrase in the answer
The last case checks memory: case 10 tells the agent "I'm Bob ...", case 11
("What are my open tasks?") must use that in a NEW conversation.

Uses your Groq quota (~4 extraction calls + ~25 agent calls).

    python eval/run_agent_eval.py
"""
import json
import re
import unicodedata

from common import EVAL_USER, ROOT, load, update_readme, use_eval_database


def main():
    print("Eval database:", use_eval_database().split("@")[-1])
    from sqlalchemy import text

    from app.agent import MeetingAgent
    from app.db.connection import SessionLocal, engine
    from app.db.init_db import init_db
    from app.pipeline import MeetingPipeline

    init_db()
    with engine.begin() as c:
        c.execute(text("TRUNCATE meetings, chunks, action_items, decisions, meeting_participants, "
                       "participants, query_logs, conversations, messages, memories RESTART IDENTITY CASCADE"))
    pipeline = MeetingPipeline()
    for m in load("meetings.json"):
        r = pipeline.process_transcript("\n".join(m["transcript"]), m["title"], EVAL_USER)
        print(f"  {m['title']}: {r['action_items']} action items, {r['decisions']} decisions")

    agent = MeetingAgent(pipeline.llm, pipeline.retriever, pipeline.embedding_agent)
    results = []
    for i, case in enumerate(load("agent_cases.json"), 1):
        db = SessionLocal()
        try:
            out = agent.chat(db, EVAL_USER, case["q"])     # each case is a new conversation
        finally:
            db.close()
        used = [s["tool"] for s in out["steps"]]
        # NFKC turns non-breaking / narrow spaces (common in model output) into plain spaces
        ans = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", out["answer"])).lower()
        tool_ok = any(t in used for t in case["tools"])
        answer_ok = all(any(p in ans for p in group) for group in case["answer_has"])
        results.append({"case": i, "question": case["q"], "tools_used": used, "tool_ok": tool_ok,
                        "answer_ok": answer_ok, "memories_used": out["memories_used"], "answer": out["answer"]})
        print(f"{i:>2}. tool={'ok' if tool_ok else 'MISS'} answer={'ok' if answer_ok else 'MISS'} "
              f"tools={used} | {case['q']}")

    n = len(results)
    tool_acc = sum(r["tool_ok"] for r in results) / n
    ans_acc = sum(r["answer_ok"] for r in results) / n
    both = sum(r["tool_ok"] and r["answer_ok"] for r in results) / n
    avg_steps = sum(len(r["tools_used"]) for r in results) / n
    table = ("| Cases | Right tool | Correct answer | Both | Avg tool calls |\n|---|---|---|---|---|\n"
             f"| {n} | {tool_acc:.0%} | {ans_acc:.0%} | {both:.0%} | {avg_steps:.1f} |\n")
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    (out / "agent.md").write_text(table)
    (out / "agent_details.json").write_text(json.dumps(results, indent=2))
    update_readme("AGENT_RESULTS", table)
    print("\n" + table)


if __name__ == "__main__":
    main()
