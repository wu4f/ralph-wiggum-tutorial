# Feature: Google Docs–Backed Website with Gemini-Powered Chat

## Feature Description

Replace the existing Codebase Execution Flow Explorer with a new web application
whose content is driven entirely by a shared Google Doc. Each tab in
the Google Doc becomes a page on the website. A Gemini-powered chat interface
lets visitors ask natural-language questions about any content on the site;
every answer includes structured source citations with clickable links to the
specific page(s) that contain the information.

## User Story

As a site visitor,
I want to browse pages whose content comes from a Google Doc and ask questions
about that content,
So that I can quickly find information and always know exactly which page
answered my question.

## Problem Statement

The site currently has a single hard-coded feature (execution-flow explorer).
The owner wants a content-managed site: non-technical authors edit a Google Doc,
and the website reflects those changes automatically. They also want visitors
to be able to query the entire site knowledge-base conversationally.

## Solution Statement

1. Connect to the Google Docs REST API (v1) using a **Google service-account
   credential** (a JSON key). The target Google Doc is shared (view access) with
   the service account's email. This works for normally-shared docs without
   OAuth user consent, unlike a bare API key which cannot read link-shared docs.
2. Read document **tabs** — each tab's title becomes the page name and its slug
   the URL path; tab body text is the page content. Read **nested child tabs**
   recursively as well (Google Docs tabs can be nested).
3. Cache the parsed tab content in memory (TTL-configurable, default 15 min);
   on cache miss re-fetch from the Docs API.
4. For chat, send **all tab content** directly in the Gemini prompt.
   `gemini-3.5-flash` has a 1 million token context window — a typical Google
   Doc is well under 100k tokens — so no embeddings, chunking, or vector search
   are needed.
5. Use Gemini **explicit context caching** (`client.caches.create`) to upload
   the system prompt + full Google Doc content once per TTL cycle, when the
   content is large enough (≥ 4096 tokens, the documented minimum for
   `gemini-3.5-flash`). Subsequent chat requests reference the cached content by
   name. **When content is below the minimum, or cache creation fails, fall back
   to inline generation** (send the full context with each request, no cache).
   The Gemini cache TTL is aligned with `DOCS_CACHE_TTL_SECONDS`.
6. Use Gemini **structured output** with a Pydantic response schema to guarantee
   the response is always a typed JSON object `{answer: str, sources: [{title,
   url}]}` — no fragile string parsing.
7. Support **multi-turn conversations**: the frontend sends the prior message
   history with each request, and the backend includes it in the Gemini
   `contents` so the model has conversational memory.
8. Serve one Flask route per tab (`/<slug>`); the first tab is also `/`. Guard
   **reserved slugs** (`chat`, `api`) and **empty slugs** so content pages never
   collide with the static `/chat` and `/api/chat` routes.
9. Expose `POST /api/chat`; every response includes `sources` — an array of
   `{title, url}` objects pointing to the actual pages the answer came from.
   Build page URLs from a configurable `SITE_BASE_URL` (falling back to the
   request host) so links are correct behind proxies/HTTPS.
10. Apply **per-IP rate limiting** to `/api/chat` (Flask-Limiter) to protect the
    paid Gemini API from abuse.
11. Mount a **floating chat widget** React island on every page (bottom-right
    corner) **except `/chat`**, and a **dedicated `/chat` page** with a
    full-screen chat experience. Every assistant message renders clickable
    source-page links.
12. Remove all learning/execution-flow code and tests, **and strip the unused
    database layer** (SQLAlchemy, Flask-Migrate, PostgreSQL, models, migrations)
    since the feature is stateless.

---

## Relevant Files

### Existing files to modify

- **`src/app/__init__.py`** — remove `AnalysisStore` wiring **and all DB
  wiring** (`db.init_app`, `Flask-Migrate`); register `ContentCache`,
  `ChatService`, and `Flask-Limiter` extensions; add the `tabs` context
  processor.
- **`src/app/config.py`** — add `GOOGLE_DOC_ID`, `GOOGLE_SERVICE_ACCOUNT_JSON`
  (path or inline JSON), `GEMINI_API_KEY`, `DOCS_CACHE_TTL_SECONDS` (default
  900), `SITE_BASE_URL`, `CHAT_RATE_LIMIT` (default `'20 per minute'`) config
  keys; remove all `LEARNING_*` keys **and all `SQLALCHEMY_*` keys**.
- **`src/app/views/__init__.py`** — unregister `learning_bp`; register
  `pages_bp` and `chat_bp`.
- **`src/app/templates/base.html`** — add responsive site nav (links to all
  pages fetched from `ContentCache` via context processor), and a
  `<div data-island="chat-widget">` mount point before `</body>` **rendered only
  when `not hide_widget`** (set true on the `/chat` page).
- **`requirements.txt`** — add `google-api-python-client`, `google-auth`,
  `google-genai`, `mistune`, `Flask-Limiter`; **remove `SQLAlchemy`,
  `Flask-Migrate`, `psycopg2-binary`**. Use the new `google-genai` package, not
  the legacy `google-generativeai`.
- **`frontend/package.json` / `frontend/tailwind.config.ts`** — add
  `@tailwindcss/typography` devDependency and register it in the Tailwind
  `plugins` array (the `prose` classes used by `page.html` require it).
- **`frontend/src/main.ts`** — register `chat-widget` and `chat-page` islands;
  remove `learning`.
- **`.env.example`** — add `GOOGLE_DOC_ID`, `GOOGLE_SERVICE_ACCOUNT_JSON`,
  `GEMINI_API_KEY`, `DOCS_CACHE_TTL_SECONDS`, `SITE_BASE_URL`, `CHAT_RATE_LIMIT`;
  remove `DATABASE_URL`.

### Existing files to delete

- `src/app/views/learning.py`
- `src/app/services/analysis_store.py`
- `src/app/services/repository_analysis.py`
- `src/app/services/code_map.py`
- `src/app/templates/learning.html`
- `src/app/models/` (entire directory — DB removed)
- `migrations/` (entire directory — DB removed)
- `frontend/src/islands/learning/` (entire directory)
- `frontend/src/learning/` (entire directory)
- `tests/test_learning_view.py`
- `tests/test_repository_analysis.py`
- `e2e/learning.spec.ts`
- `specs/codebase-execution-flow-explorer.md`

Also remove DB references from `tests/conftest.py` (no `db.create_all()` /
`drop_all()`), `script/setup` (drop the migration/createdb steps), and
`Procfile`/`script/server` if they reference migrations.

### New Files

- **`src/app/services/google_docs.py`** — `GoogleDocsService`: authenticates
  with a **service-account credential**, reads tabs (including nested child
  tabs, recursively) and per-tab body text from the Google Docs REST API v1.
  Produces collision-free, non-empty, non-reserved slugs.
- **`src/app/services/content_cache.py`** — `ContentCache`: TTL-based in-memory
  cache of `DocTab` objects. On refresh it (re)builds the Gemini context cache
  **when content meets the 4096-token minimum**, otherwise marks the content as
  "inline-only". Deletes the old Gemini cache on refresh. Exposes `get_tabs()`,
  `gemini_cache_name` (may be `None`), and `context_text`.
- **`src/app/services/chat_service.py`** — `ChatService`: builds the Gemini
  request using the cached content when available, otherwise inline; includes
  prior **conversation history** for multi-turn; returns a typed `ChatAnswer`
  from structured JSON output.
- **`src/app/views/pages.py`** — `pages_bp`: `GET /` (redirect to first tab),
  `GET /<slug>` (render tab content as HTML).
- **`src/app/views/chat.py`** — `chat_bp`: `GET /chat` (render chat page),
  `POST /api/chat` (JSON: `{question, history?}` → `{answer, sources}`),
  rate-limited.
- **`src/app/templates/page.html`** — Jinja template for a single page; renders
  tab content as Markdown-to-HTML via `mistune`; extends `base.html`.
- **`src/app/templates/chat.html`** — Jinja template for the dedicated chat
  page; extends `base.html`; sets `hide_widget = True`; mounts
  `data-island="chat-page"`.
- **`frontend/src/islands/chat-widget/index.tsx`** — island entry; mounts `ChatWidget`.
- **`frontend/src/islands/chat-widget/ChatWidget.tsx`** — collapsible floating
  chat bubble (bottom-right); renders answer + source links.
- **`frontend/src/islands/chat-page/index.tsx`** — island entry; mounts `ChatPage`.
- **`frontend/src/islands/chat-page/ChatPage.tsx`** — full-screen chat interface;
  message history; renders answer + source links.
- **`frontend/src/chat/useChat.ts`** — shared hook holding message state and the
  multi-turn send logic, reused by both islands.
- **`frontend/src/chat/api.ts`** — typed
  `askQuestion(question, history): Promise<ChatResponse>`.
- **`frontend/src/chat/types.ts`** — `ChatResponse`, `Source`, `Message` types.
- **`frontend/tests/chat/ChatWidget.test.tsx`** — vitest unit test (mocks
  `askQuestion`) so the frontend suite is non-empty.
- **`tests/test_google_docs.py`** — unit tests for `GoogleDocsService`.
- **`tests/test_content_cache.py`** — unit tests for TTL caching, Gemini cache
  lifecycle, and the small-content inline fallback.
- **`tests/test_chat_view.py`** — route tests for all endpoints.
- **`e2e/chat.spec.ts`** — end-to-end tests for page navigation and chat.

---

## Implementation Plan

### Phase 0: Spike — verify service-account access (do this first)

Before writing any feature code, confirm a Google service account can read the
target Google Doc with `includeTabsContent=True`. Create the service account,
enable the Docs API, share the doc (Viewer) with its `client_email`, and run a
throwaway script that prints the returned `tabs`. **Do not proceed until this
returns tab content.** This de-risks the single biggest external assumption.

### Phase 1: Foundation — remove old code + DB, add dependencies, update config

Remove all execution-flow learning code **and the unused database layer**,
register new packages (incl. Flask-Limiter, Tailwind typography) and config
keys, and ensure the app starts cleanly.

### Phase 2: Core Backend — Google Docs ingestion and content cache

Implement `GoogleDocsService` (service-account auth, nested tabs, safe slugs)
and `ContentCache` (Gemini cache lifecycle + token-minimum inline fallback);
wire as Flask extensions.

### Phase 3: Pages — server-rendered content pages

Implement `pages_bp`, `page.html`, and `base.html` nav (with `hide_widget`).

### Phase 4: Chat backend

Implement `ChatService` (cache-or-inline, multi-turn, structured output) and
`chat_bp` (rate-limited, history-aware).

### Phase 5: Chat frontend

Build the shared `useChat` hook, the `ChatWidget` and `ChatPage` islands; wire
into the island registry.

### Phase 6: Tests and validation

Write all unit tests (mocked external APIs), the frontend widget test, and E2E
tests; run the full suite.

---

## Step by Step Tasks

### Step 1 — Remove old learning code and the DB layer

- Delete `src/app/views/learning.py`
- Delete `src/app/services/analysis_store.py`, `repository_analysis.py`,
  `code_map.py`
- Delete `src/app/templates/learning.html`
- Delete `frontend/src/islands/learning/` and `frontend/src/learning/`
- Delete `tests/test_learning_view.py`, `tests/test_repository_analysis.py`
- Delete `e2e/learning.spec.ts`
- Delete `specs/codebase-execution-flow-explorer.md`
- Remove `AnalysisStore` import and wiring from `src/app/__init__.py`
- Remove all `LEARNING_*` config keys from `src/app/config.py`
- Remove `learning_bp` from `src/app/views/__init__.py`
- Remove `learning` entry from `frontend/src/main.ts` island registry

**Strip the database layer** (the feature is stateless):
- Delete `src/app/models/` and `migrations/`
- Remove `db.init_app(app)` and `Flask-Migrate`/`Migrate` from
  `src/app/__init__.py`
- Remove all `SQLALCHEMY_*` keys from `src/app/config.py`
- Remove `db.create_all()` / `db.drop_all()` from `tests/conftest.py`
- Remove `SQLAlchemy`, `Flask-Migrate`, `psycopg2-binary` from `requirements.txt`
- Remove `DATABASE_URL` from `.env.example`
- Remove migration/createdb steps from `script/setup`; drop any `flask db`
  invocation from `Procfile` / `script/server`

### Step 2 — Add new dependencies

In `requirements.txt` add:
```
google-api-python-client>=2.120.0
google-auth>=2.28.0
google-genai>=0.8.0
mistune>=3.0.0
Flask-Limiter>=3.5.0
```

And remove `SQLAlchemy`, `Flask-Migrate`, `psycopg2-binary`.

Note: `google-genai` is the new unified SDK (`from google import genai`).
Do **not** use the legacy `google-generativeai` package.

In `frontend/`, add the Tailwind typography plugin (the `prose` classes in
`page.html` require it):
```bash
cd frontend && npm install -D @tailwindcss/typography
```
and register it in `frontend/tailwind.config.ts`:
```typescript
import typography from '@tailwindcss/typography'
export default { /* ... */, plugins: [typography] } satisfies Config
```

Install Python deps with `pip install -r requirements.txt`.

### Step 3 — Add configuration

In `src/app/config.py` (base `Config` class), add — and remove all
`SQLALCHEMY_*` keys:

```python
GOOGLE_DOC_ID = os.environ.get('GOOGLE_DOC_ID', '')
# Path to a service-account JSON key file, OR the raw JSON itself.
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON', '')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
DOCS_CACHE_TTL_SECONDS = int(os.environ.get('DOCS_CACHE_TTL_SECONDS', '900'))
# Absolute base URL for building page links in chat sources. Falls back to the
# request host when empty.
SITE_BASE_URL = os.environ.get('SITE_BASE_URL', '')
CHAT_RATE_LIMIT = os.environ.get('CHAT_RATE_LIMIT', '20 per minute')
```

In `TestingConfig`, set:
```python
GOOGLE_DOC_ID = 'test-doc-id'
GOOGLE_SERVICE_ACCOUNT_JSON = ''   # tests mock the service entirely
GEMINI_API_KEY = 'test-gemini-key'
DOCS_CACHE_TTL_SECONDS = 9999
SITE_BASE_URL = 'http://localhost'
CHAT_RATE_LIMIT = '1000 per minute'   # effectively disabled in tests
```

Update `.env.example` (remove `DATABASE_URL`):
```
GOOGLE_DOC_ID=your_google_doc_id_here
GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/service-account.json
GEMINI_API_KEY=your_gemini_api_key_here
DOCS_CACHE_TTL_SECONDS=900
SITE_BASE_URL=
CHAT_RATE_LIMIT=20 per minute
```

> **Spike before building (Phase 2):** confirm the service account can read the
> target doc. Share the doc (Viewer) with the service account's
> `client_email`, then run a one-off script calling `documents().get(
> documentId=..., includeTabsContent=True)`. Verify it returns `tabs`. Only
> proceed once this works.

### Step 4 — Implement `GoogleDocsService`

File: `src/app/services/google_docs.py`

Authenticates with a **service account**, reads top-level **and nested child
tabs** recursively, and produces collision-free, non-empty, non-reserved slugs.

```python
"""Fetches tab content from a Google Doc via a service-account credential."""
from __future__ import annotations
import json
import os
import re
from dataclasses import dataclass
from typing import Any
from google.oauth2 import service_account
from googleapiclient.discovery import build

_SCOPES = ['https://www.googleapis.com/auth/documents.readonly']
_RESERVED_SLUGS = {'chat', 'api', 'static'}


@dataclass
class DocTab:
    tab_id: str
    title: str
    slug: str
    content: str


class GoogleDocsServiceError(Exception):
    pass


def _slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_-]+', '-', slug)
    return slug.strip('-')


def _safe_slug(title: str, index: int, seen: set[str]) -> str:
    """Return a unique, non-empty, non-reserved slug for a tab."""
    base = _slugify(title) or f'page-{index + 1}'
    if base in _RESERVED_SLUGS:
        base = f'{base}-page'
    slug = base
    suffix = 1
    while slug in seen:
        slug = f'{base}-{suffix}'
        suffix += 1
    seen.add(slug)
    return slug


def _extract_text(tab_body: dict[str, Any]) -> str:
    lines: list[str] = []
    for element in tab_body.get('content', []):
        paragraph = element.get('paragraph', {})
        if paragraph:
            parts = [
                e.get('textRun', {}).get('content', '')
                for e in paragraph.get('elements', [])
            ]
            lines.append(''.join(parts))
        table = element.get('table', {})
        if table:
            for row in table.get('tableRows', []):
                for cell in row.get('tableCells', []):
                    lines.append(_extract_text(cell))
    return ''.join(lines)


def _flatten_tabs(raw_tabs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Depth-first flatten of tabs and their childTabs."""
    flat: list[dict[str, Any]] = []
    for tab in raw_tabs:
        flat.append(tab)
        flat.extend(_flatten_tabs(tab.get('childTabs', [])))
    return flat


def _load_credentials(source: str) -> service_account.Credentials:
    if not source:
        raise GoogleDocsServiceError('GOOGLE_SERVICE_ACCOUNT_JSON is not set.')
    if os.path.isfile(source):
        return service_account.Credentials.from_service_account_file(
            source, scopes=_SCOPES)
    try:
        info = json.loads(source)
    except json.JSONDecodeError as exc:
        raise GoogleDocsServiceError(
            'GOOGLE_SERVICE_ACCOUNT_JSON is neither a file path nor valid JSON.'
        ) from exc
    return service_account.Credentials.from_service_account_info(
        info, scopes=_SCOPES)


class GoogleDocsService:
    def __init__(self, service_account_source: str, doc_id: str) -> None:
        self._source = service_account_source
        self._doc_id = doc_id

    def fetch_tabs(self) -> list[DocTab]:
        try:
            creds = _load_credentials(self._source)
            service = build('docs', 'v1', credentials=creds,
                            cache_discovery=False)
            doc = service.documents().get(
                documentId=self._doc_id,
                includeTabsContent=True,
            ).execute()
        except GoogleDocsServiceError:
            raise
        except Exception as exc:
            raise GoogleDocsServiceError(str(exc)) from exc

        tabs: list[DocTab] = []
        seen_slugs: set[str] = set()
        for index, tab in enumerate(_flatten_tabs(doc.get('tabs', []))):
            props = tab.get('tabProperties', {})
            title = props.get('title', 'Untitled')
            tab_id = props.get('tabId', '')
            slug = _safe_slug(title, index, seen_slugs)
            body = tab.get('documentTab', {}).get('body', {})
            content = _extract_text(body)
            tabs.append(DocTab(tab_id=tab_id, title=title, slug=slug,
                               content=content))
        return tabs
```

### Step 5 — Implement `ContentCache`

File: `src/app/services/content_cache.py`

On each TTL refresh, `ContentCache` rebuilds the in-memory tab list and the
Gemini context cache. The full Google Doc context is only tokenized by Gemini
once per TTL cycle. **If the content is below Gemini's 4096-token minimum for
explicit caching (or cache creation fails), `gemini_cache_name` stays `None`
and `ChatService` falls back to inline generation** using `context_text`.

```python
"""In-memory TTL cache for Google Docs tab content + Gemini context cache."""
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
            try:
                self._client.caches.delete(name=self._gemini_cache.name)
            except Exception:
                logger.warning('Failed to delete old Gemini cache', exc_info=True)
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
                    'Content (%s tokens) below cache minimum; using inline mode.',
                    token_count,
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
```

Notes:
- Views call `cache.get_tabs(request_host=request.host_url)`; when
  `SITE_BASE_URL` is configured it overrides the request host so source links
  are correct behind proxies/HTTPS.
- `count_tokens` is a lightweight call used to decide cache eligibility.

### Step 6 — Implement `ChatService`

File: `src/app/services/chat_service.py`

Uses the explicit cache when available, otherwise inline context. Supports
**multi-turn** by replaying prior history. Pydantic structured output guarantees
a `{answer, sources}` JSON response.

```python
"""Gemini chat: explicit-cache-or-inline, multi-turn, structured output."""
from __future__ import annotations
from pydantic import BaseModel
from google.genai import types
from .content_cache import ContentCache, MODEL, SYSTEM_PROMPT


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
    def __init__(self, cache: ContentCache) -> None:
        self._cache = cache

    def _history_contents(
        self, history: list[HistoryTurn]
    ) -> list[types.Content]:
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
        return ChatAnswer.model_validate_json(response.text)
```

Because `ChatService` shares the `ContentCache` instance, it always uses the
most recent cache name (or inline context) without extra coordination.

### Step 7 — Wire extensions into the app factory

In `src/app/__init__.py`:
- **Remove** `AnalysisStore`, `db.init_app(app)`, and `Flask-Migrate`/`Migrate`.
- Import `GoogleDocsService`, `ContentCache`, `ChatService`, and `Flask-Limiter`.
- Instantiate and register:

```python
from flask import request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from .services.google_docs import GoogleDocsService
from .services.content_cache import ContentCache
from .services.chat_service import ChatService

# inside create_app, after config is loaded:
docs_service = GoogleDocsService(
    service_account_source=app.config['GOOGLE_SERVICE_ACCOUNT_JSON'],
    doc_id=app.config['GOOGLE_DOC_ID'],
)
cache = ContentCache(
    docs_service=docs_service,
    gemini_api_key=app.config['GEMINI_API_KEY'],
    ttl_seconds=app.config['DOCS_CACHE_TTL_SECONDS'],
    site_base_url=app.config['SITE_BASE_URL'],
)
app.extensions['content_cache'] = cache
app.extensions['chat_service'] = ChatService(cache=cache)

limiter = Limiter(key_func=get_remote_address, app=app)
app.extensions['limiter'] = limiter   # chat view applies CHAT_RATE_LIMIT
```

Add an `@app.context_processor` that injects `tabs`. It must **never raise**
(error pages also extend `base.html`), and it should skip work for the JSON API:

```python
@app.context_processor
def inject_tabs():
    if request.path.startswith('/api/'):
        return {'tabs': [], 'hide_widget': True}
    try:
        c = app.extensions.get('content_cache')
        tabs = c.get_tabs(request.host_url) if c is not None else []
    except Exception:
        app.logger.warning('Could not load tabs for nav', exc_info=True)
        tabs = []
    return {'tabs': tabs, 'hide_widget': False}
```

### Step 8 — Implement `pages_bp`

File: `src/app/views/pages.py`

```python
from flask import Blueprint, abort, current_app, redirect, render_template, \
    request, url_for
import mistune
from ..services.content_cache import ContentCache

pages_bp = Blueprint('pages', __name__)


def _get_cache() -> ContentCache:
    cache = current_app.extensions.get('content_cache')
    if not isinstance(cache, ContentCache):
        raise RuntimeError('ContentCache is not configured.')
    return cache


@pages_bp.route('/')
def index():
    tabs = _get_cache().get_tabs(request.host_url)
    if not tabs:
        abort(503)
    return redirect(url_for('pages.page', slug=tabs[0].slug))


@pages_bp.route('/<slug>')
def page(slug: str):
    tabs = _get_cache().get_tabs(request.host_url)
    tab = next((t for t in tabs if t.slug == slug), None)
    if tab is None:
        abort(404)
    content_html = mistune.html(tab.content)
    return render_template('page.html', tab=tab, content_html=content_html)
```

Reserved slugs (`chat`, `api`) are guarded at slug-generation time in
`GoogleDocsService._safe_slug`, and Flask's static `/chat` / `/api/chat` routes
take priority over `/<slug>` regardless, so collisions cannot occur.

### Step 9 — Implement `chat_bp`

File: `src/app/views/chat.py`

Accepts multi-turn `history` and is rate-limited per IP via `CHAT_RATE_LIMIT`.

```python
from flask import Blueprint, current_app, jsonify, render_template, request
from pydantic import ValidationError, TypeAdapter
from ..services.chat_service import ChatService, HistoryTurn

chat_bp = Blueprint('chat', __name__)

_MAX_HISTORY = 20
_history_adapter = TypeAdapter(list[HistoryTurn])


def _get_chat_service() -> ChatService:
    svc = current_app.extensions.get('chat_service')
    if not isinstance(svc, ChatService):
        raise RuntimeError('ChatService is not configured.')
    return svc


def _rate_limit() -> str:
    return current_app.config['CHAT_RATE_LIMIT']


@chat_bp.route('/chat')
def chat_page():
    return render_template('chat.html')


def register_chat_rate_limit(app) -> None:
    """Apply the configured per-IP limit to the chat API (called in factory)."""
    limiter = app.extensions['limiter']
    limiter.limit(lambda: app.config['CHAT_RATE_LIMIT'])(ask)


@chat_bp.route('/api/chat', methods=['POST'])
def ask():
    body = request.get_json(silent=True) or {}
    question = (body.get('question') or '').strip()
    if not question:
        return jsonify({'error': 'question is required'}), 400
    if len(question) > 2000:
        return jsonify({'error': 'question too long'}), 400

    try:
        history = _history_adapter.validate_python(
            (body.get('history') or [])[-_MAX_HISTORY:]
        )
    except ValidationError:
        return jsonify({'error': 'invalid history'}), 400

    try:
        result = _get_chat_service().answer(
            question, request.host_url, history=history)
    except Exception:
        current_app.logger.exception('Chat failed')
        return jsonify({'error': 'chat service unavailable'}), 502
    return jsonify({'answer': result.answer,
                    'sources': [s.model_dump() for s in result.sources]})
```

Register both blueprints in `src/app/views/__init__.py`. Apply the rate limit
by decorating the `ask` view; the simplest robust approach is to attach the
limit in the factory after blueprint registration:
```python
app.extensions['limiter'].limit(app.config['CHAT_RATE_LIMIT'])(
    app.view_functions['chat.ask'])
```

### Step 10 — Create Jinja templates

**`src/app/templates/base.html`** — add nav and the widget mount (hidden on the
dedicated chat page via `hide_widget`):

```html
<nav class="bg-white border-b px-4 py-3 flex gap-4 items-center">
  {% for tab in tabs %}
    <a href="/{{ tab.slug }}" class="text-sm font-medium hover:underline">
      {{ tab.title }}
    </a>
  {% endfor %}
  <a href="/chat" class="ml-auto text-sm font-medium text-indigo-600 hover:underline">
    💬 Chat
  </a>
</nav>
...
{% if not hide_widget %}
<div data-island="chat-widget"></div>
{% endif %}
```

**`src/app/templates/page.html`** (`prose` requires the typography plugin added
in Step 2):
```html
{% extends "base.html" %}
{% block title %}{{ tab.title }}{% endblock %}
{% block content %}
<main class="max-w-4xl mx-auto px-4 py-10 prose prose-slate">
  <h1>{{ tab.title }}</h1>
  {{ content_html | safe }}
</main>
{% endblock %}
```

**`src/app/templates/chat.html`** (sets `hide_widget` so the floating widget is
not also rendered here):
```html
{% extends "base.html" %}
{% set hide_widget = True %}
{% block title %}Chat{% endblock %}
{% block content %}
<div data-island="chat-page" class="h-[calc(100vh-56px)]"></div>
{% endblock %}
```

> Note: the `inject_tabs` context processor sets `hide_widget = False` by
> default; the `{% set %}` in `chat.html` overrides it for this page.

### Step 11 — Create TypeScript types and API client

**`frontend/src/chat/types.ts`**:
```typescript
export interface Source {
  title: string
  url: string
}

export interface ChatResponse {
  answer: string
  sources: Source[]
}

export interface Message {
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
}
```

**`frontend/src/chat/api.ts`** — sends prior history for multi-turn:
```typescript
import type { ChatResponse, Message } from './types'

export async function askQuestion(
  question: string,
  history: Message[],
): Promise<ChatResponse> {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question,
      history: history.map((m) => ({ role: m.role, content: m.content })),
    }),
  })
  if (!res.ok) throw new Error(`Chat error: ${res.status}`)
  return res.json() as Promise<ChatResponse>
}
```

**`frontend/src/chat/useChat.ts`** — shared state + send logic for both islands:
```typescript
import { useState } from 'react'
import { askQuestion } from './api'
import type { Message } from './types'

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(false)

  async function send(question: string): Promise<void> {
    const history = messages
    setMessages((m) => [...m, { role: 'user', content: question }])
    setIsLoading(true)
    try {
      const res = await askQuestion(question, history)
      setMessages((m) => [
        ...m,
        { role: 'assistant', content: res.answer, sources: res.sources },
      ])
    } catch {
      setMessages((m) => [
        ...m,
        { role: 'assistant', content: 'Sorry, something went wrong.' },
      ])
    } finally {
      setIsLoading(false)
    }
  }

  return { messages, isLoading, send }
}
```

Both `ChatWidget` and `ChatPage` consume `useChat()` so multi-turn history and
source rendering are implemented once.

### Step 12 — Create `ChatWidget` island

File: `frontend/src/islands/chat-widget/ChatWidget.tsx`

A floating button (`fixed bottom-6 right-6 z-50`) that:
- Renders as a chat bubble icon when collapsed.
- Expands into a panel (`w-96 h-[32rem]`) with a message thread and input box.
- Each assistant message renders its text then source links:
  `sources.map(s => <a href={s.url}>{s.title}</a>)`.
- State: `isOpen`, `messages: Message[]`, `input`, `isLoading`.

File: `frontend/src/islands/chat-widget/index.tsx`:
```typescript
import { createRoot } from 'react-dom/client'
import { ChatWidget } from './ChatWidget'
export function mount(element: HTMLElement): void {
  element.innerHTML = ''
  createRoot(element).render(<ChatWidget />)
}
```

### Step 13 — Create `ChatPage` island

File: `frontend/src/islands/chat-page/ChatPage.tsx`

Full-screen chat UI (flex column, full height):
- Same message/input logic as `ChatWidget`.
- Messages fill available space with scroll; input pinned to bottom.
- Source links render prominently below each assistant answer.
- Empty state: "Ask me anything about this site…"

File: `frontend/src/islands/chat-page/index.tsx`:
```typescript
import { createRoot } from 'react-dom/client'
import { ChatPage } from './ChatPage'
export function mount(element: HTMLElement): void {
  element.innerHTML = ''
  createRoot(element).render(<ChatPage />)
}
```

### Step 14 — Register islands in `frontend/src/main.ts`

Replace the `learning` entry:
```typescript
const islandRegistry = {
  'chat-widget': () => import('./islands/chat-widget'),
  'chat-page':   () => import('./islands/chat-page'),
}
```

### Step 15 — Write unit tests

**`tests/test_google_docs.py`**:
- Mock `google.oauth2.service_account.Credentials` (both
  `from_service_account_file` and `from_service_account_info`) and
  `googleapiclient.discovery.build` to return a fake document with two tabs
  ("Home", "About"), one of which has a nested `childTabs` entry.
- Assert `fetch_tabs()` returns the parent **and** child tabs as `DocTab`
  objects with correct slugs and extracted text.
- Assert `_safe_slug` handles special characters, spaces, collisions
  (`about`/`about-1`), empty/punctuation-only titles (`page-N`), and reserved
  words (`chat` → `chat-page`).
- Assert `GoogleDocsServiceError` is raised when credentials are missing/invalid
  or when the API call fails.

**`tests/test_content_cache.py`**:
- Mock `GoogleDocsService.fetch_tabs` and `genai.Client`.
- Assert `get_tabs()` returns cached result on second call within TTL.
- Assert cache is rebuilt after TTL expiry (patch `datetime.now`).
- Assert old Gemini cache is deleted and a new one created on refresh **when
  `count_tokens` ≥ 4096**.
- Assert that when `count_tokens` < 4096, `gemini_cache_name` is `None` and
  `caches.create` is **not** called (inline fallback).
- Assert that when `caches.create` raises, `gemini_cache_name` is `None` and no
  exception propagates.
- Assert `SITE_BASE_URL` overrides the request host in built URLs.
- Assert `invalidate()` forces a re-fetch on the next call.

**`tests/test_chat_view.py`**:
- Mock `ContentCache` and `ChatService` in app extensions.
- `GET /` → 302 to `/<first-slug>`.
- `GET /<slug>` → 200 with tab title in body.
- `GET /<nonexistent>` → 404.
- `GET /chat` → 200 and does **not** contain a `data-island="chat-widget"`
  element (widget hidden on the chat page).
- `POST /api/chat {"question": "..."}` → 200 with `answer` and `sources` keys.
- `POST /api/chat {"question": "...", "history": [...]}` → 200; assert the
  mocked `ChatService.answer` received the parsed history.
- `POST /api/chat` empty body → 400.
- `POST /api/chat` oversized question → 400.
- `POST /api/chat` malformed history → 400.
- `POST /api/chat` when `ChatService.answer` raises → 502.

**`frontend/tests/chat/ChatWidget.test.tsx`** (keeps the vitest suite non-empty
after the learning test is deleted):
- Mock `../../src/chat/api` so `askQuestion` resolves to a fixed
  `{answer, sources}`.
- Render `ChatWidget`, open it, type a question, submit.
- Assert the user message, the assistant answer, and a source link
  (`<a href>` with the source title) all appear.

### Step 16 — Write E2E tests

File: `e2e/chat.spec.ts`

```typescript
import { test, expect } from '@playwright/test'

test.describe('Google Docs–Backed Site', () => {
  test('home page redirects to first tab and renders content', async ({ page }) => {
    await page.goto('/')
    await expect(page).not.toHaveURL('/')
    await expect(page.locator('nav')).toBeVisible()
    await expect(page.locator('main h1')).toBeVisible()
  })

  test('nav links lead to other pages', async ({ page }) => {
    await page.goto('/')
    const navLinks = page.locator('nav a')
    await expect(navLinks.first()).toBeVisible()
    await navLinks.first().click()
    await expect(page.locator('main h1')).toBeVisible()
  })

  test('chat widget is present on content pages but not on /chat', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('[data-island="chat-widget"]')).toBeAttached()
    await page.goto('/chat')
    await expect(page.locator('[data-island="chat-widget"]')).toHaveCount(0)
    await expect(page.locator('[data-island="chat-page"]')).toBeAttached()
  })

  test('chat page accepts a question and shows an answer with sources', async ({ page }) => {
    await page.goto('/chat')
    await page.getByRole('textbox').fill('What is this site about?')
    await page.getByRole('button', { name: /send/i }).click()
    await expect(
      page.locator('[aria-label="assistant message"], [aria-label="loading"]')
    ).toBeVisible({ timeout: 30000 })
  })
})
```

Note: E2E tests require `GOOGLE_DOC_ID`, `GOOGLE_SERVICE_ACCOUNT_JSON`, and
`GEMINI_API_KEY` in the environment (set them in `playwright.config.ts`'s
`webServer.env`). The first three tests pass without a live Gemini key; the
fourth needs live credentials.

### Step 17 — Run full validation suite

```bash
pip install -r requirements.txt
PYTHONPATH=src pytest tests/ -v
cd frontend && npm test
mypy src/ --ignore-missing-imports
flake8 src/ tests/
cd frontend && npm run typecheck && npm run lint
npx playwright test --reporter=list
```

---

## Testing Strategy

### Unit Tests

| File | What is tested |
|------|----------------|
| `test_google_docs.py` | Service-account auth, nested-tab flattening, text extraction, safe slugs (collisions/empty/reserved), error handling |
| `test_content_cache.py` | TTL caching, stale detection, Gemini cache lifecycle, **small-content inline fallback**, cache-failure fallback, `SITE_BASE_URL` override |
| `test_chat_view.py` | All routes (redirect, 200, 404, 400, 502), multi-turn history parsing, widget hidden on `/chat`, chat API JSON contract |
| `frontend/tests/chat/ChatWidget.test.tsx` | Widget renders, sends a question (mocked API), shows answer + source link |

All external calls (Google Docs API, Gemini) are mocked — tests run without
credentials and without network access.

### Edge Cases

- Google Doc with a single tab → home redirect goes to that one tab.
- Two tabs with identical titles → slugs deduplicated (`about`, `about-1`).
- Tab title that is empty / punctuation-only → slug becomes `page-N`.
- Tab titled "Chat" or "API" → slug becomes `chat-page` / `api-page` (no route
  collision). Static `/chat` and `/api/chat` also take priority over `/<slug>`.
- Nested child tabs → flattened and rendered as their own pages.
- Tab with empty body → page renders gracefully; chat context includes an empty
  section (harmless to Gemini).
- **Content below 4096 tokens** → no explicit cache created; chat uses inline
  context. **Cache creation fails** → same inline fallback, no error to the user.
- Gemini generation error during chat → `POST /api/chat` returns 502.
- `GOOGLE_DOC_ID` / service account not set → page routes return 503; the nav
  context processor returns `tabs=[]` so error pages still render.
- Chat `sources` list is empty → frontend renders the answer without a sources
  section, no error.
- Rate limit exceeded on `/api/chat` → Flask-Limiter returns 429.
- Behind a proxy/HTTPS → `SITE_BASE_URL` ensures source links use the correct
  external origin rather than the internal request host.

---

## Acceptance Criteria

1. A shared Google Doc's tabs (including nested child tabs) are automatically
   reflected as browsable pages within one TTL cycle (default 15 minutes).
2. The home route (`/`) redirects to the first tab's page.
3. Each page's `<title>` and `<h1>` match the corresponding Google Doc tab title.
4. The site navigation bar lists all tab titles with working links.
5. `POST /api/chat` always returns a valid JSON body with `answer` (string) and
   `sources` (array of `{title, url}` objects) — guaranteed by Pydantic schema —
   whether the explicit cache or the inline fallback is used.
6. Every source URL in the response points to an existing page on the site,
   using `SITE_BASE_URL` when configured.
7. Multi-turn works: a follow-up question that depends on the previous answer is
   handled correctly (history is sent and used).
8. The floating chat widget appears on content pages and opens into a functional
   chat panel; it is **not** rendered on `/chat`.
9. The `/chat` dedicated page provides a full-screen chat experience with message
   history and source links.
10. `/api/chat` is rate-limited per IP (returns 429 when exceeded).
11. All pytest tests pass. All vitest tests pass (suite is non-empty). mypy,
    flake8, eslint, tsc clean.
12. At least one Playwright E2E test passes with live API credentials.

---

## Validation Commands

```bash
pip install -r requirements.txt
PYTHONPATH=src pytest tests/ -v
cd frontend && npm test
mypy src/ --ignore-missing-imports
flake8 src/ tests/
cd frontend && npm run typecheck && npm run lint
npx playwright test --reporter=list
```

---

## Notes

- **Why full-context over RAG**: A Google Doc is typically well under 100k tokens.
  `gemini-3.5-flash`'s 1M-token window holds the entire doc plus question plus
  answer. This eliminates embeddings, vector math, chunking, and a second API
  call — simpler code, fewer failure modes, better answers.

- **Gemini explicit context caching with inline fallback**: When the doc is
  ≥ 4096 tokens, `ContentCache` calls `client.caches.create` once per TTL cycle
  and `ChatService` passes `cached_content=cache.name`. When it's smaller (or
  cache creation fails), `ChatService` falls back to sending the full context
  inline via `system_instruction`. Chat works either way.

- **Service-account auth (not API key)**: A bare API key cannot read
  "link-shared" docs. Use a service account: create it in Google Cloud, enable
  the Google Docs API, download the JSON key, and **share the Google Doc (Viewer)
  with the service account's `client_email`**. Verify with the Phase-2 spike
  before building further.

- **Structured output guarantees source links**: `ChatService` uses
  `response_schema=ChatAnswer` (a Pydantic model) with
  `response_mime_type='application/json'`. Gemini returns valid JSON matching the
  schema — no regex or string splitting.

- **Multi-turn**: the frontend sends prior `history` (capped at 20 turns); the
  backend replays it as `types.Content` entries (`assistant` → `model` role)
  before the new question.

- **New SDK**: Use `google-genai` (`from google import genai; client =
  genai.Client()`), not the deprecated `google-generativeai` package.

- **Source-link host**: `SITE_BASE_URL` (when set) overrides `request.host_url`
  so links are correct behind proxies/HTTPS. URLs are baked into the cached
  context, so they reflect whatever host was active when the cache was last
  built — set `SITE_BASE_URL` in production to keep this deterministic.

- **Database removed**: the feature is stateless, so SQLAlchemy, Flask-Migrate,
  PostgreSQL, `src/app/models/`, and `migrations/` are deleted. `script/setup`,
  `conftest.py`, and the `Procfile` must be updated to drop DB steps.

- **Tailwind typography**: `mistune.html()` output is styled by the `prose`
  classes, which require the `@tailwindcss/typography` plugin (added in Step 2).

- **Cost control**: `/api/chat` is rate-limited per IP via Flask-Limiter
  (`CHAT_RATE_LIMIT`, default `20 per minute`). The default limiter uses
  in-memory storage — fine for a single process; configure a shared backend
  (e.g. Redis) if running multiple workers.

- **Refresh latency**: cache refresh (Google Docs fetch + optional Gemini cache
  build) happens synchronously on the first request after TTL expiry, so one
  user occasionally waits a few seconds. Acceptable for v1; a background
  refresh thread is possible future work.

- **Orphaned Gemini caches**: created caches carry a server-side TTL and expire
  on their own; restarts may briefly leave an old cache until its TTL lapses.

- **Future work**: streaming responses via Server-Sent Events; admin cache
  invalidation endpoint; background (non-blocking) cache refresh; Redis-backed
  rate-limit storage for multi-worker deployments.
