# Implementation Plan — Google Docs–Backed Site with Gemini Chat

## Status

> **Feature implemented. Backend + frontend validation green.** The only
> remaining gap is E2E execution, which requires live external credentials not
> available in this environment (see Outstanding work).

Spec: `specs/google-docs-site-with-chat.md` (comprehensive, self-contained).
This feature **replaced** the former Codebase Execution-Flow Explorer, whose
code, tests, spec, and the entire unused database layer were removed.

## Outstanding work (sorted by priority)

- **[Blocked-by-env] Playwright E2E (`e2e/chat.spec.ts`).** All four tests are
  written and the `webServer.env` wiring passes `GOOGLE_DOC_ID`,
  `GOOGLE_SERVICE_ACCOUNT_JSON`, `GEMINI_API_KEY` through from the shell. They
  cannot be run green here because:
  - The first three tests need a Google service account that can read a shared
    Google Doc (returns ≥1 tab); without it page routes return 503.
  - The fourth additionally needs a live `GEMINI_API_KEY`.
  - Acceptance Criterion #12 ("at least one E2E passes with live credentials")
    is therefore satisfiable only in an environment that has those secrets.
  - **Why no offline fixture**: unlike the old feature, there is no
    `*_ALLOW_FIXTURE` hook — the spec deliberately keeps the service stateless
    and mocks externals only at the unit level. Adding an offline fixture mode
    would be net-new surface beyond the spec; left out intentionally.

## What was built

### Backend (`src/app/`)
- `services/google_docs.py` — `GoogleDocsService`: service-account auth
  (file path **or** inline JSON), reads top-level **and nested child tabs**
  (depth-first flatten), extracts paragraph + table text, and produces
  collision-free / non-empty / non-reserved slugs (`_safe_slug`).
- `services/content_cache.py` — `ContentCache`: TTL in-memory cache of
  `DocTab`s. On refresh it tears down the old Gemini cache and, **only when the
  context ≥ 4096 tokens**, creates a new explicit Gemini context cache; below
  the minimum (or on failure) it stays in inline mode (`gemini_cache_name` is
  `None`). `SITE_BASE_URL` overrides the request host in built source URLs.
- `services/chat_service.py` — `ChatService`: builds the Gemini request from the
  explicit cache when present, else inline (`system_instruction` + full
  context); replays prior `history` (assistant→model role) for multi-turn;
  returns a typed `ChatAnswer` via Pydantic `response_schema` (structured JSON).
- `views/pages.py` — `pages_bp`: `GET /` redirects to the first tab; `GET /<slug>`
  renders Markdown→HTML via `mistune` (503 when no tabs, 404 unknown slug).
- `views/chat.py` — `chat_bp`: `GET /chat` page; `POST /api/chat`
  (`{question, history?}` → `{answer, sources}`), validates question presence,
  length ≤ 2000, history shape (≤ 20 turns), returns 400/502 appropriately.
- `__init__.py` — wires `ContentCache`, `ChatService`, Flask-Limiter; applies
  `CHAT_RATE_LIMIT` to `chat.ask`; `inject_tabs` context processor (never raises,
  skips `/api/`). **All DB/`AnalysisStore` wiring removed.**
- `config.py` — `GOOGLE_DOC_ID`, `GOOGLE_SERVICE_ACCOUNT_JSON`, `GEMINI_API_KEY`,
  `DOCS_CACHE_TTL_SECONDS` (900), `SITE_BASE_URL`, `CHAT_RATE_LIMIT`
  (`20 per minute`). `TestingConfig` neutralises externals. **All `LEARNING_*`
  and `SQLALCHEMY_*` keys removed.**
- Templates: `base.html` (nav from `tabs` + `chat-widget` mount gated on
  `not hide_widget`), `page.html` (`prose`), `chat.html` (`hide_widget=True`,
  `chat-page` mount).

### Frontend (`frontend/src/`)
- `chat/types.ts`, `chat/api.ts` (multi-turn `askQuestion`), `chat/useChat.ts`
  (shared state + send), `chat/MessageThread.tsx` (answer + source links).
- `islands/chat-widget/` (floating bubble) and `islands/chat-page/`
  (full-screen) consume `useChat`. `main.ts` registry maps both islands.
- Tailwind `@tailwindcss/typography` plugin added for `prose`.

### Tests
- `tests/test_google_docs.py` (9), `tests/test_content_cache.py` (8),
  `tests/test_chat_view.py` (10) — **27 backend tests, all external calls
  mocked**, run without network/credentials.
- `frontend/tests/chat/ChatWidget.test.tsx` (1, mocks `askQuestion`).
- `e2e/chat.spec.ts` (4) — see Outstanding work.

## Validation results (this pass)
- `PYTHONPATH=src pytest tests/` → **27 passed**.
- `cd frontend && npm test` → **1 passed**.
- `mypy src/ --ignore-missing-imports` → clean (13 files).
- `flake8 src/ tests/` → clean.
- `npm run typecheck` (tsc) → clean. `npm run lint` (eslint) → clean.
- `npm run build` (vite) → succeeds (typography `prose` resolves).
- E2E → not run (no live credentials; see Outstanding work).

## Notes / learnings
- `google-genai` (the new unified SDK, `from google import genai`) v2.8.0 is
  installed; verified `caches.create/delete`, `models.count_tokens`,
  `models.generate_content`, `types.Create*Config`, `Content`/`Part` all exist.
- mypy strict flags the untyped `google-auth` credential constructors and the
  `Optional` `CachedContent.name` / `response.text`; handled with targeted
  `# type: ignore[no-untyped-call]` and explicit `None` guards (no blanket
  ignores).
- `vite build` empties `src/app/static/` (emptyOutDir) and removes `.gitkeep`;
  restore with `git checkout -- src/app/static/.gitkeep`. Build artifacts under
  `src/app/static/assets`, `.vite`, `manifest.json` are gitignored.
- `chat.html` uses `{% set hide_widget = True %}` to override the context
  processor's default so the floating widget is not double-rendered on `/chat`
  (covered by `test_chat_page_hides_floating_widget`).

## Out of scope (per spec)
Persistent storage / accounts, private/non-Google content sources, embeddings/
RAG (full-context instead), streaming responses (SSE), admin cache-invalidation
endpoint, background (non-blocking) refresh, Redis-backed rate-limit storage.
