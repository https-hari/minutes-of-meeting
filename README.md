# Minutes of Meeting
### AI meeting assistant: transcription, extraction, hybrid RAG and a tool-calling agent with memory

Turns meeting audio or transcripts into structured records (action items, decisions, participants),
answers questions with **hybrid retrieval + re-ranking**, and lets you talk to a **tool-calling agent**
that looks things up, updates task status and **remembers you across conversations**. Retrieval and
the agent are both measured with evals.

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
| POST | /meetings/transcript | Process a text transcript |
| POST | /meetings/audio | Process an audio file (Whisper) |
| POST | /query | RAG question; `mode`: `vector`, `keyword`, `hybrid`, `hybrid_rerank` (default) |
| POST | /agent/chat | Ask the agent: `{message, user_id, conversation_id?}` → answer, steps, memories used |
| GET | /agent/memories?user_id= | List what the agent remembers about a user |
| DELETE | /agent/memories/{id}?user_id= | Forget one fact |
| GET | /meetings | List all meetings |
| GET | /meetings/{id} | Meeting details |
| GET | /action-items | List action items |
| PATCH | /action-items/{id}/status | Update action item status |

---

## Running locally

**Prerequisites:** PostgreSQL with pgvector 0.5+, Python 3.9+, ffmpeg (only for audio)

```bash
git clone https://github.com/https-hari/minutes-of-meeting.git
cd minutes-of-meeting
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # add GROQ_API_KEY and DATABASE_URL
python -m app.db.init_db      # creates tables + search indexes (also runs on server start)

uvicorn main:app --reload --port 8000
open dashboard.html           # tabs: Overview, Action Items, Agent, Search, Add Meeting
```

The embedding model (~90 MB) and the re-ranker (~90 MB) download on first use; Whisper loads only when
you upload audio.

## Tests and evals

```bash
createdb mom_test
TEST_DATABASE_URL=postgresql://localhost/mom_test python -m pytest -q   # 23 tests, no API calls, fake models

python eval/run_retrieval_eval.py     # real models, no API calls; writes eval/results/retrieval.md
python eval/run_agent_eval.py         # uses your Groq quota; writes eval/results/agent.md
```

Evals run in a separate database (`<your db>_eval`), so your real meetings are never touched.

---
