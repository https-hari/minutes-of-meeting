"""Download and load the embedding and re-ranking models once (run at build time),
so the first real request doesn't wait for a ~170 MB download.

    python -m app.warmup
"""
from app.agents.embedding_agent import EmbeddingAgent
from app.retrieval import CrossEncoderReranker

if __name__ == "__main__":
    vec = EmbeddingAgent().embed_text("warm up")
    scores = CrossEncoderReranker().score("warm up", ["warm up", "something else"])
    print(f"Models ready: embedding dim {len(vec)}, rerank scores {[round(s, 2) for s in scores]}")
