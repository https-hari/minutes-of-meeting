import whisper
import os
from app.config import WHISPER_MODEL


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
        """
        Groups Whisper segments into meaningful chunks.

        Whisper gives us fine-grained segments (often one phrase each).
        We group them by pause gaps — if gap between segments > 1.5s
        we treat it as a new speaker turn.

        Each chunk becomes one row in the chunks table.
        """
        if not segments:
            return []

        chunks = []
        current_chunk = {
            "text":     segments[0]["text"].strip(),
            "start":    segments[0]["start"],
            "end":      segments[0]["end"],
            "speaker":  "Speaker 1"
        }

        speaker_num = 1
        GAP_THRESHOLD = 1.5  # seconds — tune this for better results

        for i in range(1, len(segments)):
            seg = segments[i]
            prev = segments[i - 1]

            gap = seg["start"] - prev["end"]

            if gap > GAP_THRESHOLD:
                # new speaker turn — save current chunk, start new one
                chunks.append(current_chunk)
                speaker_num = 2 if speaker_num == 1 else 1
                current_chunk = {
                    "text":     seg["text"].strip(),
                    "start":    seg["start"],
                    "end":      seg["end"],
                    "speaker":  f"Speaker {speaker_num}"
                }
            else:
                # same turn — append text to current chunk
                current_chunk["text"] += " " + seg["text"].strip()
                current_chunk["end"] = seg["end"]

        # don't forget the last chunk
        chunks.append(current_chunk)

        return chunks

    def _get_duration(self, segments: list) -> int:
        """Returns total duration in seconds."""
        if not segments:
            return 0
        return int(segments[-1]["end"])
