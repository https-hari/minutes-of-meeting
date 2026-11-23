# Changelog

## 3.0.0 (2026-11-24)
- Multi-user: Supabase login; every route, search and agent tool scoped to the signed-in user.
- Next.js website: meetings, meeting detail, action items, assistant with memory panel, search with sources,
  upload audio / paste transcript.
- Chrome extension: live Google Meet notes from captions, with speaker names and a visible badge.
- Groq-hosted Whisper; fastembed (ONNX) models so the API fits a 512 MB server; Render deploy.
- Repo restructured into `backend/`, `web/`, `extension/`; CI; 39 tests.

## 2.0.0 (2026-11-24)
- Hybrid retrieval (pgvector + full-text, RRF) with cross-encoder re-ranking.
- Tool-calling agent with short- and long-term memory.
- Retrieval and agent evals.

## 1.0.0 (2026-08)
- Whisper transcription, LLM extraction of action items and decisions, RAG over pgvector, dashboard.
