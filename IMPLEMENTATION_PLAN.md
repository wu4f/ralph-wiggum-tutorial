# Implementation Plan — Codebase Execution-Flow Explorer

## Status

> **Overall: 100% Complete — Feature implemented, all validation green.**

Spec: `specs/codebase-execution-flow-explorer.md` (comprehensive, self-contained).

The app no longer ships the Space Invaders game. It is now an **Execution-Flow
Explorer**: a student supplies a public GitHub repository URL, the backend
downloads and analyzes the repo, builds an execution-flow map, and quizzes the
student to order the execution steps. All unit tests (pytest + vitest), type
checks (mypy + tsc), linters (flake8 + eslint), E2E (Playwright), and the
production build pass.

---

## What was built

### Backend
- `src/app/views/learning.py` — `learning_bp`: `GET /` + `GET /learn` render
  `learning.html`; `POST /api/learning/analyses` creates a snapshot from a repo
  URL; `GET /api/learning/analyses/<id>` returns a learner-safe snapshot;
  `POST /api/learning/analyses/<id>/score` scores an ordered flow answer.
- `src/app/services/repository_analysis.py` — URL normalization (root-only
  GitHub URLs), repo ingestion (GitHub API default branch + codeload tar.gz with
  size/file/byte limits), fixture-repo loading (gated by
  `LEARNING_ALLOW_FIXTURE_REPOS`), language/framework detection, execution-flow
  detection (Flask request flows + generic Python/JS import-chain flows), and
  positional scoring with partial-credit feedback.
- `src/app/services/analysis_store.py` — in-memory, TTL-bound snapshot store
  (`LEARNING_ANALYSIS_TTL_SECONDS`); separates learner payload from answer keys.
- `src/app/services/code_map.py` — builds the de-duplicated node/edge graph from
  detected flows for the SVG map.
- `src/app/config.py` — `LEARNING_*` limits + `LEARNING_ALLOW_FIXTURE_REPOS`
  (true in `TestingConfig`).
- `src/app/__init__.py` — registers the `AnalysisStore` extension.
- `src/app/templates/learning.html` — `data-island="learning"` mount + noscript.

### Frontend
- `frontend/src/islands/learning/LearningIsland.tsx` + `index.tsx` — repo URL
  form, analysis fetch, ordered step selection, check-flow scoring UI.
- `frontend/src/learning/api.ts`, `types.ts`, `components/CodeMap.tsx` — typed
  API client + SVG execution map (`aria-label="Repository execution map"`).
- `frontend/src/main.ts` — island registry maps `learning`.

### Tests
- `tests/test_learning_view.py` (6), `tests/test_repository_analysis.py` (4) —
  routes, validation, fixture analysis, generic import-chain flows, scoring.
- `frontend/tests/learning/LearningIsland.test.tsx` (2).
- `e2e/learning.spec.ts` (3) — map fixture repo, score a correct flow, reject
  non-root URLs. `playwright.config.ts` sets `LEARNING_ALLOW_FIXTURE_REPOS=true`
  so E2E runs offline.
- `tests/fixtures/repositories/` — two deterministic fixture repos
  (`code-tour-buggy-portal`, `code-tour-clean`); excluded from pytest collection
  via `norecursedirs` in `pyproject.toml`.

---

## Validation results (all green)
- `PYTHONPATH=src pytest tests/` → 10 passed.
- `cd frontend && npm test` → 2 passed.
- `mypy src/` → clean. `flake8 src/ tests/` → clean.
- `cd frontend && npm run typecheck` (tsc) → clean. `npm run lint` → clean.
- `npx playwright test --reporter=list` → 3 passed.
- `cd frontend && npm run build` → production bundle builds clean.
- Live spot-check: `analyze_repository` returns flows for external repos
  (`pallets/click`, `psf/requests`) — confirms the generic import-chain path.

---

## Notes / learnings
- The generic import-chain fallback is what makes arbitrary repos work — earlier
  the analyzer only produced flows for the Flask + React-Islands shape (the
  "only works with ralph-wiggum repo" bug). Both paths now coexist (max 4 flows,
  Jaccard de-dup).
- Answer keys stay server-side in the snapshot store; the learner payload sorts
  steps by path so the correct order is not leaked to the client.
- Fixture repos let pytest/E2E run without live GitHub; enable them with
  `LEARNING_ALLOW_FIXTURE_REPOS` (default off in dev/prod, on in testing/E2E).
- `vite build` empties `src/app/static/` (emptyOutDir) and removes `.gitkeep`;
  restore it with `git checkout -- src/app/static/.gitkeep` after a local build.
- Run E2E with `--reporter=list` in agent/CI shells; the default `html` reporter
  opens a blocking report server. Browsers install once: `npx playwright install
  chromium`.

## Out of scope (per spec)
Persistent analyses / accounts, private repos / auth, non-GitHub hosts,
sub-path or branch URLs, multi-language flow tracing beyond Python + JS/TS
imports, AST-level call-graphs.
