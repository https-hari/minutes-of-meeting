from app.retrieval import Hit, Retriever, keyword_search, rrf_fuse, vector_search
from conftest import FakeReranker


def h(cid, src, rank):
    return Hit(cid, 1, "m", None, f"chunk {cid}", 0.0, {src: rank})


def test_rrf_rewards_agreement_between_searches():
    vec = [h(1, "vector", 1), h(2, "vector", 2), h(3, "vector", 3)]
    kw = [h(3, "keyword", 1), h(4, "keyword", 2)]
    fused = rrf_fuse(vec, kw)
    assert fused[0].chunk_id == 3                      # found by both
    assert fused[0].ranks == {"vector": 3, "keyword": 1}
    assert {x.chunk_id for x in fused} == {1, 2, 3, 4}


def test_keyword_search_finds_exact_ticket_id(db, seeded):
    hits = keyword_search(db, "what was JIRA-482 about?", k=3)
    assert hits and "JIRA-482" in hits[0].text
    assert hits[0].meeting_title == "Infra Sync"


def test_keyword_search_ignores_stopword_only_questions(db, seeded):
    assert keyword_search(db, "what is the", k=3) == []


def test_vector_search_and_meeting_filter(db, seeded, embedder):
    hits = vector_search(db, embedder.embed_query("marketing budget"), k=5, meeting_id=seeded["m1"])
    assert hits and all(x.meeting_id == seeded["m1"] for x in hits)
    assert "budget" in hits[0].text


def test_all_modes_return_ranked_hits(db, seeded, embedder):
    r = Retriever(embedder, FakeReranker())
    for mode in ("vector", "keyword", "hybrid", "hybrid_rerank"):
        hits = r.search(db, "why was the product launch moved to August", k=3, mode=mode)
        assert hits, mode
        assert "launch" in hits[0].text, mode


def test_rerank_records_how_each_chunk_was_found(db, seeded, embedder):
    hits = Retriever(embedder, FakeReranker()).search(db, "Postgres replication lag deploy", k=2)
    assert "replication" in hits[0].text
    assert "rrf_score" in hits[0].ranks and ("vector" in hits[0].ranks or "keyword" in hits[0].ranks)


def test_bad_mode_rejected(db, embedder):
    import pytest
    with pytest.raises(ValueError):
        Retriever(embedder, FakeReranker()).search(db, "x", mode="magic")
