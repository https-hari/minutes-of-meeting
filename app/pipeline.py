from app.agents.extraction_agent import ExtractionAgent
from app.agents.embedding_agent import EmbeddingAgent
from app.config import RETRIEVAL_MODE
from app.db.connection import SessionLocal
from app.llm import GroqLLM
from app.retrieval import Retriever
from app.db.models import (
    Meeting, Participant, MeetingParticipant,
    ActionItem, Decision, Chunk, QueryLog
)
from datetime import datetime


class MeetingPipeline:
    """
    Orchestrates the full meeting ingestion pipeline.

    Flow:
    1. Transcribe audio → text + chunks
    2. Extract action items, decisions, participants → structured JSON
    3. Embed each chunk → 384-dim vector
    4. Save everything to PostgreSQL atomically

    Why one pipeline class:
    - Single entry point — caller doesn't need to know about agents
    - Atomic DB write — if anything fails, nothing is saved (ACID)
    - Easy to test each stage independently
    - Maps directly to Chain of Responsibility design pattern
    """

    def __init__(self, llm=None, embedder=None, reranker=None):
        self.llm                 = llm or GroqLLM()
        self.extraction_agent    = ExtractionAgent(self.llm)
        self.embedding_agent     = embedder or EmbeddingAgent()
        self.retriever           = Retriever(self.embedding_agent, reranker)
        self._transcription      = None

    @property
    def transcription_agent(self):
        # Whisper is large and only needed for audio, so load it on first use
        if self._transcription is None:
            from app.agents.transcription_agent import TranscriptionAgent
            self._transcription = TranscriptionAgent()
        return self._transcription

    def process_audio(self, audio_path: str, title: str) -> dict:
        """
        Full pipeline from audio file to saved DB records.
        Returns summary of what was saved.
        """
        print(f"\n{'='*50}")
        print(f"Processing: {title}")
        print(f"{'='*50}")

        # STAGE 1: Transcription
        print("\n[Stage 1] Transcribing audio...")
        transcription = self.transcription_agent.transcribe(audio_path)
        print(f"  Done — {len(transcription['chunks'])} chunks, "
              f"{transcription['duration']}s duration")

        # STAGE 2: Extraction
        print("\n[Stage 2] Extracting action items and decisions...")
        extraction = self.extraction_agent.extract(
            transcription["full_text"],
            meeting_title=title
        )
        print(f"  Done — {len(extraction['action_items'])} action items, "
              f"{len(extraction['decisions'])} decisions, "
              f"{len(extraction['participants'])} participants")

        # STAGE 3: Embedding
        print("\n[Stage 3] Generating embeddings...")
        embedded_chunks = self.embedding_agent.embed_chunks(
            transcription["chunks"]
        )
        print(f"  Done — {len(embedded_chunks)} chunks embedded")

        # STAGE 4: Save to database
        print("\n[Stage 4] Saving to PostgreSQL...")
        result = self._save_to_db(
            title=title,
            transcription=transcription,
            extraction=extraction,
            embedded_chunks=embedded_chunks
        )
        print(f"  Done — meeting id: {result['meeting_id']}")

        return result

    def process_transcript(self, transcript: str, title: str) -> dict:
        """
        Pipeline from raw transcript text (skips transcription stage).
        Useful for testing without audio files.
        """
        print(f"\n{'='*50}")
        print(f"Processing transcript: {title}")
        print(f"{'='*50}")

        # build chunks from transcript lines
        chunks = self._text_to_chunks(transcript)

        print("\n[Stage 2] Extracting action items and decisions...")
        extraction = self.extraction_agent.extract(transcript, meeting_title=title)
        print(f"  Done — {len(extraction['action_items'])} action items, "
              f"{len(extraction['decisions'])} decisions")

        print("\n[Stage 3] Generating embeddings...")
        embedded_chunks = self.embedding_agent.embed_chunks(chunks)

        print("\n[Stage 4] Saving to PostgreSQL...")
        result = self._save_to_db(
            title=title,
            transcription={
                "full_text": transcript,
                "duration": None,
                "chunks": embedded_chunks
            },
            extraction=extraction,
            embedded_chunks=embedded_chunks
        )
        print(f"  Done — meeting id: {result['meeting_id']}")
        return result

    @staticmethod
    def _text_to_chunks(transcript: str) -> list:
        """
        Splits transcript by speaker turns for chunk storage.
        Detects lines starting with 'Name:' pattern.
        """
        chunks = []
        current_speaker = "Unknown"
        current_lines = []

        for line in transcript.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            if ":" in line:
                # check if it looks like a speaker label
                parts = line.split(":", 1)
                if len(parts[0].split()) <= 2:
                    # save previous chunk
                    if current_lines:
                        chunks.append({
                            "speaker": current_speaker,
                            "text": " ".join(current_lines)
                        })
                    current_speaker = parts[0].strip()
                    current_lines = [parts[1].strip()] if parts[1].strip() else []
                else:
                    current_lines.append(line)
            else:
                current_lines.append(line)

        if current_lines:
            chunks.append({
                "speaker": current_speaker,
                "text": " ".join(current_lines)
            })

        return chunks if chunks else [{"speaker": "Unknown", "text": transcript}]

    def _save_to_db(self, title: str, transcription: dict,
                    extraction: dict, embedded_chunks: list) -> dict:
        """
        Saves all extracted data to PostgreSQL in one transaction.

        Why one transaction:
        - If participant insert succeeds but action_items fails,
          we'd have orphaned data — atomic write prevents this
        - On any exception, db.rollback() undoes everything
        """
        db = SessionLocal()

        try:
            # 1. Save meeting
            meeting = Meeting(
                title=title,
                transcript=transcription["full_text"],
                summary=extraction.get("summary", ""),
                duration=transcription.get("duration"),
                date=datetime.now()
            )
            db.add(meeting)
            db.flush()  # gets the meeting.id without committing

            # 2. Save participants
            participant_map = {}  # name → Participant object
            for p in extraction.get("participants", []):
                name = p.get("name", "").strip()
                if not name:
                    continue

                # check if participant already exists
                existing = db.query(Participant).filter(
                    Participant.name == name
                ).first()

                if existing:
                    participant = existing
                else:
                    participant = Participant(name=name)
                    db.add(participant)
                    db.flush()

                participant_map[name] = participant

                # link participant to meeting
                link = MeetingParticipant(
                    meeting_id=meeting.id,
                    participant_id=participant.id
                )
                db.add(link)

            # 3. Save action items
            action_items_saved = 0
            for item in extraction.get("action_items", []):
                owner_name = item.get("owner")
                owner = participant_map.get(owner_name) if owner_name else None

                # parse deadline string to date object
                deadline = None
                if item.get("deadline"):
                    try:
                        from datetime import date
                        deadline = date.fromisoformat(item["deadline"])
                    except (ValueError, TypeError):
                        deadline = None

                action = ActionItem(
                    meeting_id=meeting.id,
                    owner_id=owner.id if owner else None,
                    description=item.get("description", ""),
                    deadline=deadline,
                    status="open"
                )
                db.add(action)
                action_items_saved += 1

            # 4. Save decisions
            decisions_saved = 0
            for d in extraction.get("decisions", []):
                decision = Decision(
                    meeting_id=meeting.id,
                    description=d.get("description", ""),
                    context=d.get("context")
                )
                db.add(decision)
                decisions_saved += 1

            # 5. Save chunks with embeddings
            chunks_saved = 0
            for chunk in embedded_chunks:
                c = Chunk(
                    meeting_id=meeting.id,
                    chunk_text=chunk["text"],
                    speaker=chunk.get("speaker"),
                    embedding=chunk.get("embedding")
                )
                db.add(c)
                chunks_saved += 1

            # commit everything at once
            db.commit()

            return {
                "meeting_id":       meeting.id,
                "title":            title,
                "participants":     len(participant_map),
                "action_items":     action_items_saved,
                "decisions":        decisions_saved,
                "chunks":           chunks_saved
            }

        except Exception as e:
            db.rollback()
            print(f"Pipeline failed, rolling back: {e}")
            raise
        finally:
            db.close()

    def query(self, question: str, meeting_id: int = None,
              mode: str = RETRIEVAL_MODE, k: int = 5) -> dict:
        """
        Answers a natural language question using RAG.

        1. Retrieve: hybrid search (pgvector + Postgres full-text), fused with
           Reciprocal Rank Fusion, re-ranked by a cross-encoder (see retrieval.py)
        2. Generate: the LLM answers only from those chunks, citing them
        3. Log the question, answer and chunk ids used
        """
        db = SessionLocal()
        try:
            hits = self.retriever.search(db, question, k=k, mode=mode, meeting_id=meeting_id)
            if not hits:
                return {"question": question, "answer": "No relevant meeting content found.",
                        "mode": mode, "sources": []}

            context = "\n\n".join(
                f"[{i}] ({h.meeting_title}) {h.speaker or 'Unknown'}: {h.text}"
                for i, h in enumerate(hits, 1)
            )
            response = self.llm.chat(
                messages=[
                    {"role": "system", "content": (
                        "You are a meeting assistant. Answer only from the numbered transcript "
                        "excerpts. Cite the excerpts you used like [1] or [2][3]. Be concise. "
                        "If the answer is not in the excerpts, say so.")},
                    {"role": "user", "content": f"Excerpts:\n\n{context}\n\nQuestion: {question}"},
                ],
                temperature=0.1, max_tokens=500,
            )
            answer = (response["content"] or "").strip()

            db.add(QueryLog(question=question, answer=answer,
                            chunk_ids_used=[h.chunk_id for h in hits], meeting_id=meeting_id))
            db.commit()

            return {"question": question, "answer": answer, "mode": mode,
                    "sources": [h.as_source() for h in hits]}
        finally:
            db.close()
