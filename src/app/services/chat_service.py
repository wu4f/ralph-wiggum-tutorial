"""Gemini chat: explicit-cache-or-inline, multi-turn, structured output.

The Pydantic ``response_schema`` guarantees Gemini returns a typed
``{answer, sources}`` JSON object, so the response never needs fragile string
parsing and every answer carries the source page links it drew from.
"""
from __future__ import annotations

from google.genai import types
from pydantic import BaseModel

from .content_cache import MODEL, SYSTEM_PROMPT, ContentCache


class Source(BaseModel):
    title: str
    url: str


class ChatAnswer(BaseModel):
    answer: str
    sources: list[Source]


class HistoryTurn(BaseModel):
    role: str          # 'user' | 'assistant'
    content: str


class ChatService:
    """Answers questions about the site content via Gemini."""

    def __init__(self, cache: ContentCache) -> None:
        self._cache = cache

    def _history_contents(
        self, history: list[HistoryTurn]
    ) -> list[types.Content]:
        """Replay prior turns as Gemini ``Content`` entries (multi-turn)."""
        role_map = {'user': 'user', 'assistant': 'model'}
        contents: list[types.Content] = []
        for turn in history:
            role = role_map.get(turn.role)
            if role and turn.content.strip():
                contents.append(types.Content(
                    role=role,
                    parts=[types.Part(text=turn.content)],
                ))
        return contents

    def answer(
        self,
        question: str,
        request_host: str,
        history: list[HistoryTurn] | None = None,
    ) -> ChatAnswer:
        # Ensure cache/context is fresh (triggers refresh if stale).
        self._cache.get_tabs(request_host)
        cache_name = self._cache.gemini_cache_name

        contents = self._history_contents(history or [])
        contents.append(types.Content(
            role='user', parts=[types.Part(text=question)]))

        if cache_name:
            config = types.GenerateContentConfig(
                cached_content=cache_name,
                response_mime_type='application/json',
                response_schema=ChatAnswer,
            )
        else:
            # Inline fallback: system prompt + full context as a system message.
            config = types.GenerateContentConfig(
                system_instruction=(
                    f"{SYSTEM_PROMPT}\n\n--- SITE CONTENT ---\n"
                    f"{self._cache.context_text}"
                ),
                response_mime_type='application/json',
                response_schema=ChatAnswer,
            )

        response = self._cache.client.models.generate_content(
            model=MODEL, contents=contents, config=config,
        )
        if not response.text:
            raise RuntimeError('Gemini returned an empty response.')
        return ChatAnswer.model_validate_json(response.text)
