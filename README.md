# Minutes of Meeting
### AI-Powered Meeting Intelligence System

Transcribes meeting audio or text, extracts action items and decisions via LLM, stores everything in PostgreSQL with vector embeddings, and answers natural language queries using RAG.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Transcription | OpenAI Whisper (local, base model) |
| LLM Extraction | Groq API — Llama 3.3 70B |
| Embeddings | sentence-transformers all-MiniLM-L6-v2 (384-dim) |
| Vector Store | PostgreSQL + pgvector |
| Backend | FastAPI + uvicorn |
| Frontend | Plain HTML dashboard (dark theme) |

---

## How It Works
---

## Database Schema (7 Tables)

| Table | Purpose |
|---|---|
| meetings | Meeting metadata, title, summary |
| participants | People identified in the meeting |
| meeting_participants | M:N junction — who attended which meeting |
| action_items | Extracted tasks with assignee, due date, status |
| decisions | Key decisions made during the meeting |
| chunks | Transcript chunks with 384-dim pgvector embeddings |
| query_logs | All RAG queries and their answers logged |

---

## Key Design Decisions

**Why pgvector over Pinecone:**
Everything stays in one system. SQL joins work natively between meetings, action_items, and chunks. No external vector DB to manage or pay for.

**Why RAG instead of full transcript in prompt:**
A 2-hour meeting transcript can exceed 50,000 tokens — expensive and slow. RAG retrieves only the 3-5 most relevant chunks via cosine similarity, then passes those to the LLM. Fast and cheap.

**Why Groq instead of OpenAI:**
Groq's free tier runs Llama 3.3 70B at ~500 tokens/second. More than sufficient for extraction and RAG with zero cost during development.

**What breaks at scale (10k meetings):**
pgvector's default IVFFLAT index degrades linearly. Fix: switch to HNSW index. Embedding generation becomes a CPU bottleneck — fix: async batch queue with Redis.

---

## API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | /meetings/transcript | Process text transcript |
| POST | /meetings/audio | Process audio file (Whisper) |
| POST | /query | RAG natural language query |
| GET | /meetings | List all meetings |
| GET | /meetings/{id} | Get meeting details |
| GET | /action-items | List all action items |
| PATCH | /action-items/{id}/status | Update action item status |

---

## Running Locally

**Prerequisites:** PostgreSQL 16 + pgvector, Python 3.9+, ffmpeg

```bash
# Clone and setup
git clone https://github.com/https-hari/minutes-of-meeting.git
cd minutes-of-meeting
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Environment variables
cp .env.example .env
# Add your GROQ_API_KEY and DATABASE_URL to .env

# Run
uvicorn main:app --reload --port 8000

# Open dashboard
open dashboard.html
```

---

## Project Structure
