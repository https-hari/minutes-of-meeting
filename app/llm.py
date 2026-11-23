"""Thin wrapper over the Groq chat API.

Everything else talks to an object with one method, `chat(messages, tools=None,
json_mode=False)`, that returns a plain dict:

    {"content": str | None, "tool_calls": [{"id", "name", "arguments"}]}

Keeping the provider behind this shape means the agent and tests never touch
the SDK directly (tests pass a scripted fake), and switching provider is one file.
"""
from __future__ import annotations

import time

from app.config import GROQ_API_KEY, LLM_MODEL


class GroqLLM:
    def __init__(self, model: str = LLM_MODEL, max_retries: int = 3):
        from groq import Groq   # imported here so tests don't need the SDK configured
        if not GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is not set (add it to .env)")
        self.client = Groq(api_key=GROQ_API_KEY)
        self.model = model
        self.max_retries = max_retries

    def chat(self, messages: list[dict], tools: list[dict] | None = None,
             json_mode: bool = False, temperature: float = 0.1, max_tokens: int = 1500) -> dict:
        import groq

        kwargs = dict(model=self.model, messages=messages, temperature=temperature,
                      max_tokens=max_tokens)
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if "gpt-oss" in self.model:
            kwargs["reasoning_effort"] = "low"   # hidden reasoning tokens count against rate limits

        for attempt in range(self.max_retries + 1):
            try:
                resp = self.client.chat.completions.create(**kwargs)
                break
            except groq.RateLimitError as e:
                if attempt == self.max_retries:
                    raise
                headers = getattr(getattr(e, "response", None), "headers", {}) or {}
                try:
                    wait = float(headers.get("retry-after"))
                except (TypeError, ValueError):
                    wait = 2 ** attempt
                time.sleep(min(wait, 30))
            except groq.BadRequestError as e:
                # a tool call or JSON the provider itself rejected: retry once without JSON mode
                if json_mode and "json_validate_failed" in str(e) and attempt < self.max_retries:
                    kwargs.pop("response_format", None)
                    continue
                raise

        msg = resp.choices[0].message
        calls = [{"id": c.id, "name": c.function.name, "arguments": c.function.arguments or "{}"}
                 for c in (msg.tool_calls or [])]
        return {"content": msg.content, "tool_calls": calls}
