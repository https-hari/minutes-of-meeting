# AGENTS.md

Instructions for AI coding agents (Claude Code, Codex, Cursor, Copilot, etc.) working in this repo.
Humans: see [README.md](README.md) and [CONTRIBUTING.md](CONTRIBUTING.md).

## What this is

Minutes turns meetings (live Google Meet captions, audio, or transcripts) into action items, decisions
and a searchable record, with an agent that answers questions about them. Three parts:

| Part | Path | Tech |
|---|---|---|
| API | `backend/` | Python 3.12, FastAPI, SQLAlchemy 2, PostgreSQL + pgvector, Groq, fastembed |
| Website | `web/` | Next.js 15 (App Router), TypeScript, Tailwind v4, Supabase Auth (client side) |
| Extension | `extension/` | Chrome MV3, plain JavaScript, no build step |

## Commands

```bash
# backend (run from backend/)
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
TEST_DATABASE_URL=postgresql://localhost/mom_test python -m pytest -q   # must pass; no network
uvicorn main:app --reload --port 8000                                   # needs backend/.env
python eval/run_retrieval_eval.py --fake                                # eval harness check, offline
python eval/run_retrieval_eval.py   # real models, no API calls
python eval/run_agent_eval.py       # uses Groq quota: ask the user first

# web (run from web/)
npm install && npm run dev
npm run build                        # also type-checks; must pass

# extension
for f in extension/*.js extension/*/*.js; do node --check "$f"; done
```

## Map

```
backend/app/api/routes.py   every HTTP route; all except /health require a user (Depends(current_user))
backend/app/auth.py         verifies Supabase JWTs (JWKS or legacy HS256); AUTH_DISABLED=1 -> user "local"
backend/app/pipeline.py     ingest: transcript/audio -> extraction -> chunks + embeddings -> one DB transaction
backend/app/retrieval.py    vector + keyword search, RRF fusion, cross-encoder re-rank; always filtered by user
backend/app/agent.py        tool specs, Pydantic arg validation, the tool-calling loop
backend/app/memory.py       conversations (short-term), per-user facts with embeddings (long-term)
backend/app/llm.py          the only place that talks to Groq (chat, tools, JSON mode, retries)
backend/app/db/init_db.py   CREATE EXTENSION, tables, indexes, idempotent upgrades (MIGRATIONS)
web/lib/api.ts              typed API client; adds the Supabase access token
extension/content/meet.js   reads Meet captions; Meet's DOM changes often: keep selectors in findRegion/readBlocks
extension/background.js     session storage + token refresh + upload; approves new websites before connecting
```

## Invariants: do not break

1. **Every query is scoped to the signed-in user.** Any new route, tool or SQL must filter by
   `Meeting.user_id == user.id` (directly or via a join). Another user's id must return 404, never data.
   Add a test in `backend/tests/test_api.py` for each new route.
2. **The LLM never writes data directly.** It calls validated tools; only `update_action_item` writes,
   and only whitelisted statuses.
3. **Tests never touch the network.** Use `tests/fakes.py` (FakeEmbedder, FakeReranker, ScriptedLLM).
4. **Schema changes need an idempotent upgrade** in `init_db.MIGRATIONS` (`ADD COLUMN IF NOT EXISTS`, backfill),
   because existing databases are upgraded on start.
5. **Keep the server under 512 MB RAM** (Render free): fastembed/ONNX by default; don't import torch,
   sentence-transformers or whisper at module level.
6. **Secrets stay out of the repo and out of the browser.** Only `NEXT_PUBLIC_*` values reach the website,
   and the Supabase service-role key is never used anywhere.
7. **The extension shows a visible indicator whenever it captures a meeting**, and only starts on a user click.

## Conventions

- Python: type hints, `from __future__ import annotations` in new modules, small functions, comments explain *why*.
- API responses: `{"success": true, "data": ...}`; errors via `HTTPException` with a message a user can act on.
- Web: client components, Tailwind utility classes, shared styles via `@utility` in `globals.css`
  (Tailwind v4 cannot `@apply` plain classes). Copy in sentence case; buttons say what they do.
- Bug fixes come with a test that failed before the fix.

## Ask the user before

- Running the agent eval or anything else that spends API quota
- Adding dependencies (backend must stay small; extension has none)
- Changing the database schema or the API contract used by `web/lib/api.ts` and the extension
- Committing, pushing, or deploying. Commits are made from the user's own GitHub account.
