"""Hybrid retrieval with re-ranking.

Why not vector search alone:
- Embeddings match meaning ("money" ~ "budget") but are weak on exact tokens:
  names, ticket ids (JIRA-482), versions (v2.3), numbers.
- Keyword search (Postgres full-text) is the opposite.

So we run both, merge them with Reciprocal Rank Fusion, and re-order the
merged top candidates with a cross-encoder, which reads the question and the
chunk together (slower, much more accurate) instead of comparing two vectors.

    question ─┬─ vector search  (pgvector, top 20) ─┐
              └─ keyword search (tsvector, top 20) ─┴─ RRF ─ top 20 ─ cross-encoder ─ top k
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import text

from app.config import MODEL_BACKEND, MODEL_CACHE_DIR, RERANK_MODEL, RETRIEVAL_CANDIDATES

MODES = ("vector", "keyword", "hybrid", "hybrid_rerank")
RRF_K = 60   # standard constant from the RRF paper; damps the weight of top ranks


@dataclass
class Hit:
    chunk_id: int
    meeting_id: int
    meeting_title: str
    speaker: str | None
    text: str
    score: float = 0.0
    ranks: dict = field(default_factory=dict)   # which searches found it, and at what rank

    def as_source(self) -> dict:
        return {"chunk_id": self.chunk_id, "meeting_id": self.meeting_id,
                "meeting_title": self.meeting_title, "speaker": self.speaker,
                "text": self.text, "score": round(self.score, 4), "found_by": self.ranks}


_BASE = """
    SELECT c.id, c.meeting_id, m.title, c.speaker, c.chunk_text, {score} AS score
    FROM chunks c JOIN meetings m ON m.id = c.meeting_id
    WHERE m.user_id = :uid AND {where} {meeting_filter}
    ORDER BY score {order}
    LIMIT :k
"""


def _rows_to_hits(rows, source: str) -> list[Hit]:
    return [Hit(r.id, r.meeting_id, r.title, r.speaker, r.chunk_text, float(r.score), {source: i + 1})
            for i, r in enumerate(rows)]


def vector_search(db, query_vec: list[float], k: int, meeting_id: int | None = None,
                  user_id: str = "local") -> list[Hit]:
    sql = _BASE.format(score="c.embedding <=> CAST(:vec AS vector)", where="c.embedding IS NOT NULL",
                       meeting_filter="AND c.meeting_id = :mid" if meeting_id else "", order="ASC")
    vec = "[" + ",".join(f"{v:.6f}" for v in query_vec) + "]"
    rows = db.execute(text(sql), {"vec": vec, "k": k, "mid": meeting_id, "uid": user_id}).fetchall()
    hits = _rows_to_hits(rows, "vector")
    for h in hits:
        h.score = 1 - h.score                # cosine distance -> similarity
    return hits


def keyword_search(db, question: str, k: int, meeting_id: int | None = None,
                   user_id: str = "local") -> list[Hit]:
    # plainto_tsquery drops stop words and stems, but ANDs every term, which is too strict
    # for full questions; turning the ANDs into ORs lets ts_rank_cd reward chunks with more terms.
    tsq = "to_tsquery('english', replace(plainto_tsquery('english', :q)::text, '&', '|'))"
    sql = _BASE.format(score=f"ts_rank_cd(to_tsvector('english', c.chunk_text), {tsq})",
                       where=f"to_tsvector('english', c.chunk_text) @@ {tsq}",
                       meeting_filter="AND c.meeting_id = :mid" if meeting_id else "", order="DESC")
    if not db.execute(text("SELECT plainto_tsquery('english', :q)::text <> ''"), {"q": question}).scalar():
        return []                            # question was only stop words
    rows = db.execute(text(sql), {"q": question, "k": k, "mid": meeting_id, "uid": user_id}).fetchall()
    return _rows_to_hits(rows, "keyword")


def rrf_fuse(*result_lists: list[Hit], k: int = RRF_K) -> list[Hit]:
    """Reciprocal Rank Fusion: score = sum over lists of 1 / (k + rank).

    Uses ranks, not raw scores, so a cosine similarity and a ts_rank never
    have to be put on the same scale.
    """
    merged: dict[int, Hit] = {}
    for hits in result_lists:
        for rank, h in enumerate(hits, 1):
            m = merged.setdefault(h.chunk_id, Hit(h.chunk_id, h.meeting_id, h.meeting_title,
                                                  h.speaker, h.text, 0.0, {}))
            m.score += 1.0 / (k + rank)
            m.ranks.update(h.ranks)
    return sorted(merged.values(), key=lambda h: h.score, reverse=True)


class CrossEncoderReranker:
    """Scores (question, chunk) pairs jointly. Loaded on first use (~90 MB)."""

    def __init__(self, model_name: str = RERANK_MODEL, backend: str = MODEL_BACKEND):
        self.model_name, self.backend = model_name, backend
        self._model = None

    def score(self, question: str, texts: list[str]) -> list[float]:
        if self._model is None:
            if self.backend == "fastembed":
                from fastembed.rerank.cross_encoder import TextCrossEncoder
                # same weights, exported to ONNX by Xenova
                name = "Xenova/" + self.model_name.split("/")[-1] if self.model_name.startswith("cross-encoder/") else self.model_name
                self._model = TextCrossEncoder(model_name=name, cache_dir=MODEL_CACHE_DIR)
            else:
                from sentence_transformers import CrossEncoder
                self._model = CrossEncoder(self.model_name)
        if self.backend == "fastembed":
            return [float(s) for s in self._model.rerank(question, texts)]
        return [float(s) for s in self._model.predict([(question, t) for t in texts])]


class Retriever:
    def __init__(self, embedder, reranker=None, candidates: int = RETRIEVAL_CANDIDATES):
        self.embedder = embedder
        self.reranker = reranker or CrossEncoderReranker()
        self.candidates = candidates

    def search(self, db, question: str, k: int = 5, mode: str = "hybrid_rerank",
               meeting_id: int | None = None, user_id: str = "local") -> list[Hit]:
        """Only chunks from meetings owned by user_id are ever considered."""
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        n = max(k, self.candidates)

        if mode == "keyword":
            return keyword_search(db, question, k, meeting_id, user_id)
        vec_hits = vector_search(db, self.embedder.embed_query(question), n, meeting_id, user_id)
        if mode == "vector":
            return vec_hits[:k]

        fused = rrf_fuse(vec_hits, keyword_search(db, question, n, meeting_id, user_id))[:n]
        if mode == "hybrid" or not fused:
            return fused[:k]

        scores = self.reranker.score(question, [h.text for h in fused])
        for h, s in zip(fused, scores):
            h.ranks["rrf_score"] = round(h.score, 4)
            h.score = s
        return sorted(fused, key=lambda h: h.score, reverse=True)[:k]
