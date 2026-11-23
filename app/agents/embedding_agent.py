from app.config import EMBEDDING_MODEL


class EmbeddingAgent:
    """
    Converts text into vectors using a local sentence-transformer model.

    What is an embedding:
    - A list of 384 floating point numbers representing the meaning of text
    - "budget proposal" and "financial plan" will have very similar vectors
      even though they share no words — the model understands semantics
    - This is how the query "what did we decide about money?" can find
      chunks about "budget" and "revenue" — meaning over keywords

    Why all-MiniLM-L6-v2:
    - 384 dimensions — small enough to be fast, large enough to be accurate
    - Runs entirely locally on M1 — no API cost
    - 22MB model size — downloads once, cached forever
    - Good balance of speed and quality for this use case
    """

    def __init__(self):
        from sentence_transformers import SentenceTransformer   # heavy; imported only when used
        print(f"Loading embedding model: {EMBEDDING_MODEL}")
        self.model = SentenceTransformer(EMBEDDING_MODEL)
        print("Embedding model ready.")

    def embed_text(self, text: str) -> list:
        """
        Converts a single string to a vector.
        Returns a Python list of 384 floats.
        """
        vector = self.model.encode(text, convert_to_numpy=True)
        return vector.tolist()

    def embed_chunks(self, chunks: list) -> list:
        """
        Embeds a list of chunk dicts.
        Each chunk gets an 'embedding' field added to it.

        We batch all texts together — sentence-transformers
        is faster when processing multiple texts at once
        because it can parallelize on M1's neural engine.
        """
        texts = [chunk["text"] for chunk in chunks]

        print(f"Embedding {len(texts)} chunks...")
        vectors = self.model.encode(texts, convert_to_numpy=True)

        for i, chunk in enumerate(chunks):
            chunk["embedding"] = vectors[i].tolist()

        print("Embedding complete.")
        return chunks

    def embed_query(self, query: str) -> list:
        """
        Embeds a user query for similarity search.
        Same model, same vector space — so query vectors
        are directly comparable to chunk vectors.
        """
        return self.embed_text(query)
