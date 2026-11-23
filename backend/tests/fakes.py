"""Fake embedder, re-ranker and LLM: used by the tests and by `eval --fake`."""
import hashlib
import json
import math
import re

WORD = re.compile(r"[a-z0-9]+")


class FakeEmbedder:
    """Bag-of-words hashed into 384 dims. Shared words -> similar vectors."""
    def embed_text(self, t):
        v = [0.0] * 384
        for w in WORD.findall(t.lower()):
            if len(w) > 2:
                v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 384] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]
    embed_query = embed_text

    def embed_chunks(self, chunks):
        for c in chunks:
            c["embedding"] = self.embed_text(c["text"])
        return chunks


class FakeReranker:
    """Scores by how many question words appear in the chunk."""
    def score(self, q, texts):
        qw = set(WORD.findall(q.lower()))
        return [float(len(qw & set(WORD.findall(t.lower())))) for t in texts]


class ScriptedLLM:
    """Returns the given replies in order; records what it was sent."""
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def chat(self, messages, tools=None, **kw):
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools})
        r = self.replies.pop(0)
        if isinstance(r, str):
            return {"content": r, "tool_calls": []}
        return {"content": None, "tool_calls": [
            {"id": f"call_{i}", "name": n, "arguments": json.dumps(a) if isinstance(a, dict) else a}
            for i, (n, a) in enumerate(r)]}


def tool_call(*calls):
    """tool_call(("get_action_items", {"owner": "Alice"})) -> one model turn with tool calls."""
    return list(calls)
