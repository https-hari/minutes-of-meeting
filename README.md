# Minutes of Meeting
### AI meeting assistant: transcription, extraction, hybrid RAG and a tool-calling agent with memory

Turns meeting audio or transcripts into structured records (action items, decisions, participants),
answers questions with **hybrid retrieval + re-ranking**, and lets you talk to a **tool-calling agent**
that looks things up, updates task status and **remembers you across conversations**. Retrieval and
the agent are both measured with evals.

It is a complete product: a **website** with login (Next.js + Supabase Auth), a **Chrome extension**
that takes notes in live Google Meet calls, and a **FastAPI backend** where every user only ever sees
their own meetings.

```
Chrome extension (Google Meet captions) ─┐
Website: upload audio / paste transcript ┼──► FastAPI (login check, per-user data) ──► Postgres + pgvector
Website: meetings, tasks, assistant      ─┘            │
                                                       └──► Groq: Whisper, gpt-oss (extraction, agent)
```

---

## What's new in v3: a working product

| | v2 | v3 |
|---|---|---|
| Users | One local user | **Login** (email/password or Google via Supabase); every query scoped to the signed-in user, other users' ids return 404 |
| Interface | Single HTML dashboard | **Next.js website**: meetings, meeting detail with highlighted decisions, action items board, assistant chat with memory panel, search with sources, upload (drag-and-drop audio, paste transcript) |
| Live meetings | None | **Chrome extension** for Google Meet: reads captions with real speaker names, visible "taking notes" badge, saves to your account and opens the meeting |
| Transcription | Local Whisper (~1 GB) | **Groq hosted Whisper** (`whisper-large-v3-turbo`) by default; local still available |
| Tests | 24 | **39** (auth, isolation between users, live captions, uploads) |

---

## What's new in v2

| | v1 | v2 |
|---|---|---|
| Retrieval | pgvector cosine only | **Hybrid**: pgvector + Postgres full-text, fused with **Reciprocal Rank Fusion**, re-ranked by a **cross-encoder** |
| Answering | One RAG call | **Agent** that chooses tools in a loop (search, action items, decisions, update status, save memory) |
| Memory | None | Short-term (conversation history) + long-term (per-user facts with embeddings, recalled by relevance) |
| Quality | Manual checks | **Retrieval eval** (Recall@k, MRR across 4 search modes) and **agent eval** (tool choice + answer correctness), 23 pytest tests |
| Model | `llama-3.3-70b-versatile` (retired by Groq) | `openai/gpt-oss-120b`, configurable |
| Schema | 7 tables | 10 tables (+ conversations, messages, memories) |

---

## Results

Retrieval eval: 32 questions over 4 meetings (76 transcript chunks); each question has exactly one
correct chunk. Searching across all meetings.

<!-- RETRIEVAL_RESULTS -->
| Search | Recall@1 | Recall@3 | Recall@5 | MRR | R@3 paraphrase | R@3 exact-token | ms/query |
|---|---|---|---|---|---|---|---|
| vector | 59% | 84% | 84% | 0.72 | 80% | 100% | 9 |
| keyword | 53% | 84% | 88% | 0.68 | 73% | 100% | 2 |
| hybrid | 53% | 91% | 94% | 0.71 | 87% | 100% | 18 |
| hybrid_rerank | 69% | 91% | 100% | 0.80 | 87% | 100% | 50 |
<!-- /RETRIEVAL_RESULTS -->

Agent eval: 11 questions; a case passes when the agent calls a sensible tool **and** the answer
contains the right facts. The last case checks that a fact saved in one conversation is used in a new one.

<!-- AGENT_RESULTS -->
| Cases | Right tool | Correct answer | Both | Avg tool calls |
|---|---|---|---|---|
| 11 | 100% | 100% | 100% | 1.2 |
<!-- /AGENT_RESULTS -->

---

## How it works

```
INGEST
audio ──Whisper──► transcript ──► speaker-turn chunks ──MiniLM──► 384-dim vectors ─┐
                       │                                                          ├─► PostgreSQL + pgvector
                       └──Groq LLM (JSON mode)──► action items, decisions, people ─┘    (one transaction)

ASK (/query)
question ─┬─ vector search  (pgvector HNSW, top 20) ─┐
          └─ keyword search (tsvector GIN,  top 20) ─┴─ RRF ─► top 20 ─► cross-encoder ─► top 5 ─► LLM answer with [n] citations

AGENT (/agent/chat)
message + recalled memories + last 10 messages
   └─► LLM ──tool calls──► search_meetings · get_action_items · get_decisions ·
        ▲                  list_meetings · update_action_item · save_memory
        └──── results ◄────┘   (repeat, max 6 steps) ──► answer + the steps it took
```

---

## Database Schema (10 tables)

| Table | Purpose |
|---|---|
| meetings | Meeting metadata, title, summary |
| participants | People identified in meetings |
| meeting_participants | M:N junction: who attended which meeting |
| action_items | Extracted tasks with owner, deadline, status (`open` / `in_progress` / `done`) |
| decisions | Decisions made, with the reason |
| chunks | Transcript chunks with 384-dim embeddings; GIN full-text index + HNSW vector index |
| query_logs | Every RAG question, answer and chunk ids used |
| conversations | One per agent chat session, owned by a user |
| messages | Short-term memory: the turns of each conversation |
| memories | Long-term memory: per-user facts with embeddings |

---

## Key design decisions

**Why hybrid search instead of vectors alone:** embeddings match meaning ("cloud bill" finds "AWS cost")
but are weak on exact tokens such as ticket ids (`JIRA-482`), versions (`1.22`) and names. Postgres
full-text search is the opposite. Running both covers both kinds of question.

**Why Reciprocal Rank Fusion:** a cosine similarity and a `ts_rank` score are on different scales, so
adding them is meaningless. RRF uses only each chunk's *rank* in each list (`1 / (60 + rank)`), so a
chunk that both searches rank highly rises to the top.

**Why a cross-encoder re-ranker:** the embedding model encodes question and chunk separately, which is
fast but approximate. A cross-encoder reads them *together* and scores relevance much more accurately,
but is too slow to run on every chunk, so it only re-orders the top 20 candidates.

**Why the agent uses tools instead of one big prompt:** structured questions ("what does Alice still
have open?") are answered exactly by SQL over `action_items`; open questions ("why did we move the
launch?") need transcript search. Letting the model pick the tool gives exact answers for the first
kind and grounded ones for the second.

**How the agent stays safe:**
- Every tool's arguments are validated with Pydantic; a bad call sends the error back so the model can fix it.
- Unknown tools are reported, not executed.
- Only one tool writes (`update_action_item`), and only to the three allowed statuses.
- A hard step limit stops loops; on the last step tools are withheld so it must answer.
- A conversation can only be continued by the user who started it.

**Why two kinds of memory:** the last 10 messages give follow-ups context ("and the second one?").
Lasting facts ("I'm Bob, I own the launch timeline") are stored with an embedding, and only the 3 most
relevant are recalled per question, so memory can grow without filling the prompt. Near-duplicate
facts update the existing one instead of piling up.

**Why pgvector over Pinecone:** one system. SQL joins work natively between meetings, action items,
chunks and memories, in one transaction. Nothing external to run or pay for.

**Why Groq:** fast and free for development. The provider sits behind one small wrapper (`app/llm.py`),
so swapping it is one file.

**What breaks at scale (10k meetings):** embedding on ingest becomes the bottleneck (fix: background
queue); the cross-encoder adds ~100-300 ms per query on CPU (fix: cache, or re-rank fewer candidates);
`query_logs` and `messages` grow without limit (fix: retention policy).

---

## API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
All routes except `/health` need `Authorization: Bearer <Supabase access token>` and only see the
caller's data.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | /health | Liveness check (public) |
| GET | /me | The signed-in user |
| POST | /meetings/transcript | Process a text transcript |
| POST | /meetings/audio | Process an audio file (form: `title`, `file`; max 25 MB) |
| POST | /meetings/live | Captions from the extension: `{title, captions: [{speaker, text}]}` |
| GET | /meetings | Your meetings, with open action item counts |
| GET | /meetings/{id} | Meeting detail: summary, participants, decisions, action items, transcript |
| DELETE | /meetings/{id} | Delete a meeting and everything derived from it |
| GET | /action-items?status= | Your action items across meetings |
| PATCH | /action-items/{id}/status | Update status (`open`, `in_progress`, `done`) |
| POST | /query | RAG question; `mode`: `vector`, `keyword`, `hybrid`, `hybrid_rerank` (default) |
| POST | /agent/chat | Ask the agent: `{message, conversation_id?}` → answer, steps, memories used |
| GET | /agent/memories | What the agent remembers about you |
| DELETE | /agent/memories/{id} | Forget one fact |

---

## Repository layout

```
backend/            FastAPI API (Python)
  app/              api/routes.py · auth.py · pipeline.py · retrieval.py · agent.py · memory.py · llm.py
  app/agents/       transcription (Whisper) · extraction (LLM → JSON) · embedding
  app/db/           models (10 tables) · connection · init_db (extension, indexes, upgrades)
  tests/            pytest suite: real Postgres, fake models and LLM
  eval/             retrieval + agent benchmarks and their results
web/                Next.js website (login, meetings, tasks, assistant, search)
extension/          Chrome extension for live Google Meet notes
docs/DEPLOY.md      Supabase + Render + Vercel, step by step
legacy/             the original single-file dashboard
render.yaml         one-click backend deploy (Render Blueprint)
```

## Running locally

**Prerequisites:** PostgreSQL with pgvector 0.5+, Python 3.10+, Node.js 20+

**1. Backend**
```bash
git clone https://github.com/https-hari/minutes-of-meeting.git
cd minutes-of-meeting/backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # GROQ_API_KEY and DATABASE_URL; AUTH_DISABLED=1 skips login locally
uvicorn main:app --reload --port 8000
```
Tables, indexes and upgrades from older versions run on start (existing meetings are kept and assigned
to the user `local`). The embedding model and re-ranker (~170 MB, ONNX) download on first use.

**2. Website**
```bash
cd web
cp .env.example .env.local    # leave the Supabase values empty to run without login
npm install
npm run dev                   # http://localhost:3000
```

**3. Chrome extension**: `chrome://extensions` → Developer mode → **Load unpacked** → `extension/`.
Open the website's **Chrome extension** page and click **Connect**. In a Google Meet call, turn on
captions and click **Start taking notes**.

**Deploying** (Supabase + Render + Vercel, all free, no card): see [docs/DEPLOY.md](docs/DEPLOY.md).

## Tests and evals

From `backend/`:
```bash
createdb mom_test
TEST_DATABASE_URL=postgresql://localhost/mom_test python -m pytest -q   # 39 tests, no API calls, fake models

python eval/run_retrieval_eval.py     # real models, no API calls; writes eval/results/retrieval.md
python eval/run_agent_eval.py         # uses your Groq quota; writes eval/results/agent.md
```

Evals run in a separate database (`<your db>_eval`), so your real meetings are never touched.
CI runs the tests, the website build and an extension check on every push.

---
