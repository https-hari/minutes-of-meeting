import os

from app.config import GROQ_API_KEY, GROQ_WHISPER_MODEL, WHISPER_MODEL

GAP_THRESHOLD = 1.5   # seconds of silence treated as a new speaker turn


def build_chunks(segments: list) -> list:
    """Group Whisper segments into turns: a pause longer than GAP_THRESHOLD starts a new chunk.

    Whisper does not identify speakers, so turns alternate 'Speaker 1' / 'Speaker 2'.
    (Live meetings from the extension do have real names, from the captions.)
    """
    if not segments:
        return []
    chunks, speaker = [], 1
    cur = {"text": segments[0]["text"].strip(), "start": segments[0]["start"],
           "end": segments[0]["end"], "speaker": "Speaker 1"}
    for prev, seg in zip(segments, segments[1:]):
        if seg["start"] - prev["end"] > GAP_THRESHOLD:
            chunks.append(cur)
            speaker = 2 if speaker == 1 else 1
            cur = {"text": seg["text"].strip(), "start": seg["start"], "end": seg["end"],
                   "speaker": f"Speaker {speaker}"}
        else:
            cur["text"] += " " + seg["text"].strip()
            cur["end"] = seg["end"]
    chunks.append(cur)
    return chunks


class GroqTranscriber:
    """Hosted Whisper (large-v3-turbo) on Groq: no local model, fast, deployable on small servers."""

    def __init__(self, model: str = GROQ_WHISPER_MODEL):
        from groq import Groq
        self.client = Groq(api_key=GROQ_API_KEY)
        self.model = model

    def transcribe(self, audio_path: str) -> dict:
        with open(audio_path, "rb") as f:
            resp = self.client.audio.transcriptions.create(
                file=(os.path.basename(audio_path), f.read()), model=self.model,
                response_format="verbose_json", temperature=0.0)
        data = resp.model_dump() if hasattr(resp, "model_dump") else dict(resp)
        segments = data.get("segments") or []
        return {
            "full_text": (data.get("text") or "").strip(),
            "language": data.get("language"),
            "duration": int(segments[-1]["end"]) if segments else int(data.get("duration") or 0),
            "chunks": build_chunks(segments) or [{"speaker": "Speaker 1", "text": (data.get("text") or "").strip()}],
        }


class TranscriptionAgent:
    """
    Converts audio files to text using OpenAI Whisper running locally.

    Why Whisper:
    - Runs entirely on your machine, no API cost
    - Supports multiple languages
    - The 'base' model is fast enough for demos on M1
    - Larger models (small, medium, large) give better accuracy
      but take more time — trade-off you can discuss in interviews
    """

    def __init__(self):
        print(f"Loading Whisper model: {WHISPER_MODEL}")
        # model is loaded once and reused
        # loading takes ~5 seconds, inference is fast after that
        import whisper   # ~1 GB with torch; only imported for TRANSCRIBE_PROVIDER=local
        self.model = whisper.load_model(WHISPER_MODEL)
        print("Whisper model ready.")

    def transcribe(self, audio_path: str) -> dict:
        """
        Takes path to audio file, returns structured transcript.

        Whisper returns:
        - text: full transcript as one string
        - segments: list of timed segments with start/end timestamps
        - language: detected language

        We use segments to create speaker-turn chunks.
        Note: Whisper base does not do speaker diarization
        (identifying WHO said what). For a real system you'd
        add pyannote-audio for diarization. For this project
        we label speakers as 'Speaker 1', 'Speaker 2' etc.
        based on natural pause gaps — good enough for demos.
        """

        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        print(f"Transcribing: {audio_path}")

        # fp16=False because M1 MPS can have issues with fp16
        # on CPU this runs fine with fp32
        result = self.model.transcribe(audio_path, fp16=False)

        # extract segments and group into chunks
        # each chunk is roughly one sentence or speaker turn
        chunks = self._build_chunks(result["segments"])

        return {
            "full_text":  result["text"].strip(),
            "language":   result["language"],
            "duration":   self._get_duration(result["segments"]),
            "chunks":     chunks
        }

    def _build_chunks(self, segments: list) -> list:
        return build_chunks(segments)

    def _get_duration(self, segments: list) -> int:
        """Returns total duration in seconds."""
        if not segments:
            return 0
        return int(segments[-1]["end"])
