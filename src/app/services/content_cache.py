"""In-memory TTL cache for Google Docs tab content + Gemini context cache.

Why full-context over RAG: a Google Doc is typically well under 100k tokens and
``gemini-3.5-flash`` has a 1M-token window, so the entire doc fits in a single
prompt. This removes embeddings, chunking and vector search entirely.

Why an explicit Gemini cache: tokenizing the whole doc on every chat request is
wasteful. We upload the system prompt + full content once per TTL cycle via
``caches.create`` and reference it by name. Below Gemini's 4096-token minimum
(or if cache creation fails) we fall back to inline generation so chat still
works — see :class:`~app.services.chat_service.ChatService`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from google import genai
from google.genai import types

from .google_docs import DocTab, GoogleDocsService

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a helpful assistant for this website. The full content of every page
is provided as context, each section labelled with its page title and URL.
Answer questions using only this content. Be concise and accurate. Populate
`sources` with the title and URL of every page your answer draws from.
"""

MODEL = 'gemini-3.5-flash'
# Documented minimum input tokens for explicit caching on gemini-3.5-flash.
MIN_CACHE_TOKENS = 4096


class ContentCache:
    """TTL-bound cache of Google Doc tabs plus the Gemini context cache."""

    def __init__(
        self,
        docs_service: GoogleDocsService,
        gemini_api_key: str,
        ttl_seconds: int,
        site_base_url: str = '',
    ) -> None:
        self._service = docs_service
        self._client = genai.Client(api_key=gemini_api_key)
        self._ttl = ttl_seconds
        self._site_base_url = site_base_url
        self._tabs: list[DocTab] = []
        self._context_text: str = ''
        self._cached_at: datetime | None = None
        self._gemini_cache: types.CachedContent | None = None

    @property
    def gemini_cache_name(self) -> str | None:
        return self._gemini_cache.name if self._gemini_cache else None

    @property
    def context_text(self) -> str:
        return self._context_text

    @property
    def client(self) -> genai.Client:
        return self._client

    def _is_stale(self) -> bool:
        if self._cached_at is None:
            return True
        age = (datetime.now(timezone.utc) - self._cached_at).total_seconds()
        return age > self._ttl

    def _resolve_base_url(self, request_host: str) -> str:
        return (self._site_base_url or request_host).rstrip('/')

    def _build_context(self, base_url: str) -> str:
        parts: list[str] = []
        for tab in self._tabs:
            url = f"{base_url}/{tab.slug}"
            parts.append(f"## {tab.title}\nURL: {url}\n\n{tab.content}")
        return '\n\n---\n\n'.join(parts)

    def refresh(self, request_host: str) -> None:
        """Fetch tabs and (re)create the Gemini context cache when eligible."""
        base_url = self._resolve_base_url(request_host)
        self._tabs = self._service.fetch_tabs()
        self._context_text = self._build_context(base_url)
        self._cached_at = datetime.now(timezone.utc)

        # Tear down any previous Gemini cache.
        if self._gemini_cache is not None:
            old_name = self._gemini_cache.name
            if old_name:
                try:
                    self._client.caches.delete(name=old_name)
                except Exception:
                    logger.warning('Failed to delete old Gemini cache',
                                   exc_info=True)
            self._gemini_cache = None

        # Only create an explicit cache when content meets the token minimum.
        try:
            token_count = self._client.models.count_tokens(
                model=MODEL, contents=self._context_text
            ).total_tokens or 0
            if token_count >= MIN_CACHE_TOKENS:
                self._gemini_cache = self._client.caches.create(
                    model=MODEL,
                    config=types.CreateCachedContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        contents=[self._context_text],
                        ttl=f'{self._ttl}s',
                    ),
                )
            else:
                logger.info(
                    'Content (%s tokens) below cache minimum; using inline '
                    'mode.', token_count,
                )
        except Exception:
            # Inline fallback — chat still works, just without explicit caching.
            logger.warning('Gemini cache creation failed; using inline mode.',
                           exc_info=True)
            self._gemini_cache = None

    def get_tabs(self, request_host: str = '') -> list[DocTab]:
        """Return tabs, refreshing from Google Docs + Gemini cache if stale."""
        if self._is_stale():
            self.refresh(request_host)
        return self._tabs

    def invalidate(self) -> None:
        self._cached_at = None
