import json

from app.llm import GroqLLM


class ExtractionAgent:

    def __init__(self, llm=None):
        self.llm = llm or GroqLLM()

    def extract(self, transcript: str, meeting_title: str = "") -> dict:
        prompt = self._build_prompt(transcript, meeting_title)

        response = self.llm.chat(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a precise meeting analyst. "
                        "You extract structured information from meeting transcripts. "
                        "You always respond with valid JSON only. "
                        "No explanations, no markdown, no code blocks. "
                        "Just the raw JSON object."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            json_mode=True,
            temperature=0.1,
            max_tokens=2000
        )

        raw = (response["content"] or "").strip()
        return self._parse_response(raw)

    def _build_prompt(self, transcript: str, meeting_title: str) -> str:
        return f"""
Analyze this meeting transcript and extract the following information.

Meeting title: {meeting_title or "Unknown"}

Transcript:
{transcript}

Extract and return a JSON object with exactly this structure:
{{
    "participants": [
        {{"name": "string"}}
    ],
    "action_items": [
        {{
            "description": "string — what needs to be done",
            "owner": "string — person responsible, or null",
            "deadline": "string — YYYY-MM-DD format if mentioned, or null"
        }}
    ],
    "decisions": [
        {{
            "description": "string — what was decided",
            "context": "string — why it was decided, or null"
        }}
    ],
    "summary": "string — 2-3 sentences summarizing the meeting"
}}

Rules:
- Include ALL people mentioned by name in participants
- An action item is any commitment or follow-up, even implicit ones
- A decision is any conclusion or agreement reached
- Return ONLY the JSON object, nothing else
"""

    def _parse_response(self, raw: str) -> dict:
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1])

        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"Failed to parse LLM response: {e}")
            print(f"Raw response was: {raw}")
            return {
                "participants": [],
                "action_items": [],
                "decisions": [],
                "summary": "Could not parse meeting summary."
            }
