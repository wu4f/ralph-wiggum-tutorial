# Feature: Codebase Execution-Flow Explorer

## Feature Description
The Codebase Execution-Flow Explorer is a web app that helps students learn to
navigate large, unfamiliar codebases. A student pastes a public GitHub
repository URL; the app downloads and statically analyzes the repository, builds
an **execution-flow map** (an undirected graph of files/modules), and quizzes the
student to click the files **in the order they execute** for each discovered
flow. The app then scores the student's ordering and returns partial-credit
feedback plus the correct order.

The app is served as the homepage of the Flask + React Islands application. The
backend performs all repository ingestion, flow detection, and scoring; the
frontend is a single React island that renders an SVG code map, the repo URL
form, the ordered-step selection UI, and the scoring results. There is **no
database persistence** of analyses — each analysis is a short-lived, in-memory
snapshot with a TTL.

This feature replaces the previous "Space Invaders" demo entirely.

## User Story
As a student learning to read large codebases
I want to point the app at a public GitHub repository and be quizzed on the
order in which its files execute for a given trigger (e.g. an HTTP request or a
module load)
So that I build an intuition for tracing execution flow through real projects.

## Problem Statement
Reading a large, unfamiliar codebase is hard: it is not obvious where execution
begins or how control passes from file to file. Static file browsers show
structure but not *flow*. Students need an interactive way to (a) see a bounded
map of the files involved in a concrete execution path and (b) actively recover
the order those files run, with immediate, graded feedback.

An earlier iteration of the analyzer only produced flows for repositories shaped
exactly like this Flask + React Islands tutorial (the "ralph-wiggum" shape):
Flask route → Jinja template → `data-island` → frontend `main.ts` → island
component. That meant arbitrary repositories produced **no flows** and the quiz
was unusable for them. The explorer must work for *any* reasonable repository,
not just the tutorial's own shape.

## Solution Statement
Build a backend analysis pipeline and a thin React island:

1. **Validate** the repository URL strictly (root GitHub URLs only).
2. **Ingest** the repo by reading its default branch and downloading the
   `tar.gz` source archive (or, in tests, reading a local fixture repository),
   applying hard size/file-count/byte limits and skipping binary/vendored/test
   content.
3. **Detect execution flows** with two strategies:
   - **Framework request flows** (high signal): Flask route → template →
     `data-island` → `frontend/src/main.ts` → island component.
   - **Generic import-chain flows** (fallback, so *any* repo works): resolve
     Python and JS/TS imports into a module graph, score entry-point
     candidates, and walk the longest import chain from each entry.
   Cap the result at **4 flows**, de-duplicating near-identical flows by Jaccard
   similarity of their step sets.
4. **Separate learner payload from answer key**: the learner sees steps
   **shuffled (sorted by path)** and an **undirected** graph (no arrows that
   would reveal order); the correct execution order is kept **server-side** in
   the snapshot so the student cannot read the answer from the API/DOM.
5. **Store** each analysis as an in-memory snapshot with a TTL — no DB.
6. **Score** a submitted ordering by **positional correctness**, returning a
   score, max score, an `isCorrect` flag, partial-credit feedback, and the
   correct order for reveal.
7. **Render** a React island: repo URL form, summary chips, flow selector, an
   SVG code map whose nodes the student clicks to build an order, a "Check flow"
   action, and a results panel that reveals the correct order.

### Why these design decisions
- **In-memory, short-lived snapshots (TTL):** analyses are derived from public
  repos and only needed for the duration of a quiz session. Keeping them in
  memory with a TTL avoids storing third-party source code in a database
  (privacy / data-retention), keeps the system stateless across restarts, and
  needs no migrations.
- **Answer keys kept server-side:** if the correct order were sent to the
  browser, a student could read it from the network payload or DOM. The learner
  payload deliberately omits ordering (steps sorted by path, graph edges
  undirected); only `/score` reveals the answer, and only after a submission.
- **Generic import-chain fallback:** the explicit bug this fixes was "only works
  with the ralph-wiggum repo." Framework request-flow detection is high-signal
  but narrow. The import-chain fallback guarantees that arbitrary Python and
  JS/TS repositories still produce at least one meaningful flow.
- **Fixture repositories + `LEARNING_ALLOW_FIXTURE_REPOS`:** unit and E2E tests
  must be deterministic and run offline (no live GitHub calls, no flakiness, no
  rate limits). Fixture repos owned by `copilot-fixtures` are read from disk and
  are only honored when the flag is enabled (true in the testing config).
- **Bounded everything (flows, depth, bytes, files):** untrusted, arbitrarily
  large public repos must not exhaust memory or time. Hard caps keep ingestion
  and analysis safe.

## Relevant Files
Use these files to understand and maintain the feature. All paths exist in the
current codebase.

**Backend**
- `src/app/__init__.py` — App factory; instantiates `AnalysisStore` from
  `LEARNING_ANALYSIS_TTL_SECONDS` into `app.extensions['analysis_store']`;
  registers blueprints and error handlers.
- `src/app/config.py` — `LEARNING_*` settings (TTL, ingestion limits, fixture
  flag). `TestingConfig` sets `LEARNING_ALLOW_FIXTURE_REPOS = True`.
- `src/app/views/__init__.py` — Registers `learning_bp`.
- `src/app/views/learning.py` — The learning blueprint: homepage shell render +
  the three JSON API endpoints (create / get / score). Validates request
  payloads and maps `RepositoryAnalysisError` to HTTP 400.
- `src/app/services/repository_analysis.py` — URL normalization, default-branch
  lookup, archive/fixture ingestion with limits, framework + import-chain flow
  detection, learner-payload vs answer-key construction, and `score_flow`.
- `src/app/services/analysis_store.py` — `AnalysisSnapshot` dataclass and
  `AnalysisStore` (thread-safe, in-memory, TTL eviction).
- `src/app/services/code_map.py` — `build_execution_graph`: union of flow steps
  → undirected display graph (intentionally omits direction).
- `src/app/errors.py` — JSON/HTML-aware 400/404/500 error handlers (API returns
  `{ "error", "message" }`).
- `src/app/templates/learning.html` — Homepage shell extending `base.html` with
  the `data-island="learning"` mount point and "Execution Flow Explorer" copy.

**Frontend**
- `frontend/src/main.ts` — Island registry / auto-mount; registers
  `learning: () => import('./islands/learning')`.
- `frontend/src/islands/learning/index.tsx` — Island entry; mounts
  `<LearningIsland />` into the DOM node.
- `frontend/src/islands/learning/LearningIsland.tsx` — Main React component:
  repo URL form, `analysis_id` deep-link load, summary chips, flow selector,
  ordered-step state, "Check flow"/"Reset", results panel.
- `frontend/src/learning/api.ts` — `createAnalysis`, `getAnalysis`, `scoreFlow`
  fetch helpers; error-message extraction.
- `frontend/src/learning/types.ts` — `AnalysisPayload`, `CodeGraph`,
  `GraphNode`, `GraphEdge`, `Flow`, `FlowStep`, `AnalysisSummary`,
  `FlowScoreResult`.
- `frontend/src/learning/components/CodeMap.tsx` — SVG code map: radial node
  layout, clickable nodes, order badges, correct-order reveal with arrows.

**Tests & fixtures**
- `tests/test_learning_view.py` — Route/API tests (homepage shell, `/learn`
  alias, create payload, non-root URL rejection, scoring round-trip, unknown
  flow rejection).
- `tests/test_repository_analysis.py` — Analysis/scoring unit tests (request
  flow ordering, undirected edges, scoring rewards/penalties, snapshot TTL
  expiry).
- `frontend/tests/learning/LearningIsland.test.tsx` — Vitest component tests
  (maps a repo and renders quiz; scores a flow when nodes are ordered).
- `e2e/learning.spec.ts` — Playwright tests (map fixture repo, score a correct
  order, reject non-root URL).
- `tests/fixtures/repositories/code-tour-buggy-portal/` — Flask + Islands
  fixture producing the canonical request flow
  `views/dashboard.py → templates/dashboard.html → frontend/src/main.ts →
  islands/dashboard/index.tsx`.
- `tests/fixtures/repositories/code-tour-clean/` — Second fixture (clean
  portal, home flow) for deterministic offline analysis.

## API Contract

All endpoints live under the `learning` blueprint and return JSON when the
client sends `Accept: application/json`. Errors use the shared handler shape
`{ "error": "...", "message": "..." }`.

### `GET /` and `GET /learn`
Render the `learning.html` homepage shell (the React island mount point). Both
routes serve the same shell.

### `POST /api/learning/analyses`
Create a fresh analysis snapshot.
- Request body: `{ "repositoryUrl": "https://github.com/{owner}/{repo}" }`.
- `400` if `repositoryUrl` is missing/blank or fails analysis (invalid URL,
  unreachable repo, too large, etc.).
- `201` with the **learner payload** on success:
  ```json
  {
    "analysisId": "<hex>",
    "expiresAt": "<iso8601>",
    "repository": { "owner", "repo", "url", "defaultBranch" },
    "summary": { "languages": [...], "frameworks": [{id,label}], "fileCount", "flowCount" },
    "graph": { "nodes": [{id,label,path,kind}], "edges": [{id,sourceId,targetId,label}] },
    "flows": [{ "id", "title", "trigger", "prompt", "steps": [{id,label,path,kind}] }],
    "flowsAvailable": true
  }
  ```
  Flow `steps` are **sorted by path** (not execution order). The graph is
  **undirected** (deduped by either edge orientation). The answer key is **not**
  included.

### `GET /api/learning/analyses/<analysis_id>`
Return a previously created snapshot's learner payload (used for `?analysis_id=`
deep links).
- `404` if the snapshot does not exist or has expired.
- `200` with the same learner-payload shape as create.

### `POST /api/learning/analyses/<analysis_id>/score`
Score an ordering against the server-side answer key.
- Request body: `{ "flowId": "<id>", "orderedStepIds": ["file:...", ...] }`.
- `404` if the snapshot is missing/expired.
- `400` if `flowId` is not a string, `orderedStepIds` is not a list of strings,
  or the `flowId` is unknown for this snapshot.
- `200` with:
  ```json
  {
    "flowId": "...",
    "score": <int>,
    "maxScore": <int>,
    "isCorrect": <bool>,
    "feedback": "...",
    "correctOrder": [{ "id", "label", "path", "kind" }, ...]
  }
  ```

## Implementation Plan

### Phase 1: Configuration & Store
Define `LEARNING_*` config (TTL + ingestion limits + fixture flag), wire an
`AnalysisStore` into the app factory under `app.extensions['analysis_store']`,
and ensure JSON-aware error handlers are registered.

### Phase 2: Repository Ingestion
Implement strict URL normalization, default-branch resolution via the GitHub
API, `tar.gz` download via codeload with byte/file limits, binary/text and
skip-directory filtering, and the fixture-repo path gated behind
`LEARNING_ALLOW_FIXTURE_REPOS`.

### Phase 3: Flow Detection & Payload Construction
Implement framework request-flow detection and the generic import-chain
fallback, the `_MAX_FLOWS` cap with Jaccard de-duplication, the undirected
display graph (`code_map.build_execution_graph`), and the learner-payload /
answer-key split.

### Phase 4: API Endpoints
Implement the three endpoints in `learning.py`, validating inputs and mapping
`RepositoryAnalysisError` → 400, missing snapshots → 404.

### Phase 5: Frontend Island
Implement `LearningIsland` (form, deep-link load, flow selector, ordered-step
state, results), the `CodeMap` SVG component, the `api.ts` fetch helpers, and
register the island in `main.ts`.

### Phase 6: Tests
Add backend route/unit tests, Vitest component tests, and Playwright E2E tests,
all driven by deterministic fixture repositories.

## Step by Step Tasks

### Step 1: Config and snapshot store
- Add `LEARNING_ANALYSIS_TTL_SECONDS` (default 1800), `LEARNING_MAX_ARCHIVE_BYTES`
  (40 MiB), `LEARNING_MAX_EXTRACTED_BYTES` (120 MiB), `LEARNING_MAX_ANALYZED_FILES`
  (4000), `LEARNING_MAX_FILE_BYTES` (512 KiB), and `LEARNING_ALLOW_FIXTURE_REPOS`
  (false by default; true in `TestingConfig`).
- Implement `AnalysisStore(ttl_seconds)` with `save()` / `get()` and lock-guarded
  TTL eviction; instantiate it in `create_app`.

### Step 2: URL normalization
- Accept only `https://github.com/{owner}/{repo}` with exactly two path
  segments, no query, no fragment. Strip a trailing `.git`.
- Reject `tree/…`, `blob/…`, query strings, fragments, and non-github hosts with
  a `RepositoryAnalysisError` whose message begins "Only root GitHub repository
  URLs are supported" (for the non-two-segment case).
- If fixtures are allowed and the owner is `copilot-fixtures` and the fixture
  directory exists, mark the ref as a fixture; otherwise call the GitHub API for
  the default branch.

### Step 3: Ingestion
- Fixture path: read files under `tests/fixtures/repositories/<repo>/`, applying
  skip rules and size/file limits.
- Live path: download `tar.gz` from
  `https://codeload.github.com/{owner}/{repo}/tar.gz/refs/heads/{branch}`, cap at
  `LEARNING_MAX_ARCHIVE_BYTES`, then per-member enforce `LEARNING_MAX_FILE_BYTES`,
  skip binary (NUL byte) content, strip the top-level archive directory, skip
  vendored/build/test/hidden directories and non-text suffixes, and cap total
  extracted bytes and file count.

### Step 4: Flow detection
- **Request flows:** for each `.py` file with both a `@*.route("…")` and a
  `render_template("…")`, build view → `src/app/templates/<name>` → (if the
  template has `data-island="x"`) → `frontend/src/main.ts` → island module
  resolved from the `main.ts` island registry.
- **Import-chain flows:** build a module graph from Python (`from`/`import`
  resolution against a dotted-module map, including `src.`/`lib.` roots) and
  JS/TS (`import … from`, dynamic `import()`, `require()`, re-exports), score
  entry candidates (entry filenames, `__main__`, `Flask(`/`FastAPI(`,
  `create_app`, routes, `app.listen(`/`createServer`), and walk the longest
  chain (depth ≤ `_MAX_CHAIN_DEPTH`).
- Cap at `_MAX_FLOWS` (4); skip a chain flow if its step set is >0.6 Jaccard
  similar to an already-accepted flow. If nothing qualifies but a chain of ≥2
  exists, emit that as a last-resort flow.

### Step 5: Payload split & graph
- Build `learner_payload` (repository, summary, undirected `graph`, `flows` with
  steps sorted by path, `flowsAvailable`) and `answer_keys`
  (`flows[id] = { orderedStepIds, stepLookup }`).
- `build_execution_graph` unions step nodes and consecutive-step edges, deduping
  edges regardless of orientation (no direction revealed).

### Step 6: Scoring
- `score_flow(answer_keys, flow_id, ordered_step_ids)`: raise on unknown flow;
  count positionally-correct entries; `isCorrect` only when length matches and
  every position is correct; produce tiered feedback (all correct / none correct
  / partial `N of M`); return the correct order via `stepLookup`.

### Step 7: API endpoints
- Implement `index` (renders shell at `/` and `/learn`), `create_analysis`,
  `get_analysis`, `score_analysis` in `learning.py`, using the snapshot store
  and validating inputs as described in the API contract.

### Step 8: Frontend
- `api.ts`: `createAnalysis`, `getAnalysis`, `scoreFlow` with error extraction.
- `LearningIsland.tsx`: URL form → `createAnalysis`, update URL to
  `/?analysis_id=…`; on mount, load `?analysis_id` via `getAnalysis`; per-flow
  order map and result map; click nodes to toggle order; "Check flow" →
  `scoreFlow`; "Reset" clears order/result; results panel reveals correct order.
- `CodeMap.tsx`: radial SVG layout, clickable nodes (role="button", aria-label
  `"<label> (<kind>)"`), order badges, and correct-order reveal with arrowed
  edges.
- Register `learning` in `main.ts`.

### Step 9: Tests & fixtures
- Provide `copilot-fixtures` fixture repos and write backend, Vitest, and
  Playwright tests per the Testing Strategy.

### Step 10: Validation
- Run the validation commands below; all must pass.

## Testing Strategy

### Backend unit tests (`tests/test_repository_analysis.py`)
- `analyze_repository` on the buggy-portal fixture detects a request flow whose
  learner steps are sorted by path and whose canonical order starts at
  `file:src/app/views/dashboard.py` and ends at
  `file:frontend/src/islands/dashboard/index.tsx`.
- The display graph's edges only reference present node ids (undirected pairs).
- `score_flow` returns `isCorrect` + full score for the correct order and a
  lower, non-correct score for the reversed order.
- `AnalysisStore` returns a saved snapshot and evicts it once expired.

### Backend route tests (`tests/test_learning_view.py`)
- `GET /` and `GET /learn` render the shell containing "Execution Flow Explorer"
  and `data-island="learning"`.
- `POST /api/learning/analyses` with the fixture URL returns `201`, the repo
  name, `flowsAvailable: true`, non-empty `flows`/`graph.nodes`, and an
  `analysisId`.
- A `…/tree/main` URL returns `400` with "Only root GitHub repository URLs are
  supported".
- Round-trip: create → score the known correct order → `isCorrect: true`,
  `score == maxScore`.
- Unknown `flowId` → `400`.

### Frontend component tests (`frontend/tests/learning/LearningIsland.test.tsx`)
- Filling the URL and clicking "Map repository" renders the flow prompt, the SVG
  map (`aria-label="Repository execution map"`), and the prompt text.
- Clicking nodes in order then "Check flow" shows "Score 2/2" and the correct
  feedback. `fetch` is mocked (no network).

### E2E tests (`e2e/learning.spec.ts`)
- Map the buggy-portal fixture → "files analyzed", "Request to /" heading, and
  the SVG map appear.
- Click `dashboard.py → dashboard.html → main.ts → index.tsx`, then "Check
  flow" → "Score 4/4" and success feedback.
- A `/tree/main` URL surfaces the non-root rejection message.

Tests run **offline** because `LEARNING_ALLOW_FIXTURE_REPOS` is enabled in the
testing config and the fixtures live under `tests/fixtures/repositories/`.

## Edge Cases
- **Non-root / decorated URLs:** `tree/…`, `blob/…`, query strings, fragments,
  trailing `.git`, and non-`github.com` hosts are rejected with clear messages.
- **Repository not found / GitHub unreachable:** HTTP/URL errors during
  default-branch lookup or archive download become a `400` with a friendly
  message.
- **Oversized repositories:** archive bytes, total extracted bytes, per-file
  bytes, and file counts are all capped; exceeding any cap yields a "too large"
  message.
- **Binary and vendored content:** files containing NUL bytes are skipped;
  `.git`, `node_modules`, `dist`, `build`, `.venv`, hidden dirs, etc. and
  non-text suffixes are excluded.
- **No detectable flow:** `flowsAvailable` is `false`; the UI shows a
  "no execution flow detected" message instead of a quiz.
- **Non-Flask repos:** the import-chain fallback still yields a flow for generic
  Python and JS/TS projects (this is the core "works for any repo" guarantee).
- **Duplicate/near-duplicate flows:** suppressed via Jaccard similarity > 0.6.
- **Expired or missing analysis id:** `GET`/`score` return `404`; the UI surfaces
  the error.
- **Cheating prevention:** learner payload steps are sorted by path and the graph
  is undirected; the correct order is only returned by `/score`.
- **Partial submissions / wrong length:** scored by position; `isCorrect`
  requires exact length and all positions correct.

## Acceptance Criteria
1. `GET /` and `GET /learn` render the explorer shell with the
   `data-island="learning"` mount point (`tests/test_learning_view.py`).
2. `POST /api/learning/analyses` with a valid fixture URL returns `201` and a
   learner payload with repository info, summary, an undirected graph, flows
   with path-sorted steps, `flowsAvailable: true`, and an `analysisId`
   (`tests/test_learning_view.py`, `tests/test_repository_analysis.py`).
3. Non-root GitHub URLs (e.g. `…/tree/main`) are rejected with `400` and the
   "Only root GitHub repository URLs are supported" message
   (`tests/test_learning_view.py`, `e2e/learning.spec.ts`).
4. The canonical request flow for the buggy-portal fixture is
   view → template → `main.ts` → island, with learner steps sorted by path and
   the answer key held server-side (`tests/test_repository_analysis.py`).
5. The generic import-chain fallback produces a flow for repositories that are
   not Flask + Islands shaped (covered by the analyzer's entry/chain logic).
6. Scoring returns positional score, `maxScore`, `isCorrect`, tiered feedback,
   and the correct order; a correct ordering scores full marks and a reversed
   ordering does not (`tests/test_repository_analysis.py`,
   `tests/test_learning_view.py`).
7. Analysis snapshots are in-memory and expire after the TTL; `GET`/`score` on a
   missing/expired id return `404` (`tests/test_repository_analysis.py`).
8. The React island maps a repository, renders the SVG code map, lets the student
   build an order by clicking nodes, and shows the score/feedback after "Check
   flow" (`frontend/tests/learning/LearningIsland.test.tsx`,
   `e2e/learning.spec.ts`).
9. All validation commands pass with zero errors.

## Validation Commands
Execute every command to validate the feature works correctly with zero
regressions.

```bash
# Install dependencies (first time only)
script/bootstrap

# Backend + frontend unit tests (pytest + vitest)
script/test

# TypeScript + Python type checking (mypy + tsc)
script/typecheck

# Linting (flake8 + eslint)
script/lint

# End-to-end browser tests (Playwright; auto-starts dev servers)
script/test-e2e
```

Direct equivalents (when not using the wrapper scripts):

```bash
PYTHONPATH=src pytest tests/
cd frontend && npm test
mypy src/ --ignore-missing-imports
cd frontend && npm run typecheck
flake8 src/ tests/
cd frontend && npm run lint
npx playwright test --reporter=list   # use list reporter in non-interactive shells
```

## Notes
- **No database.** Analyses are intentionally ephemeral; only the in-memory
  `AnalysisStore` holds them, evicting on TTL. This avoids retaining third-party
  source and keeps the system stateless across restarts.
- **Security/abuse hardening.** Every ingestion dimension is bounded
  (`LEARNING_MAX_*`). Binary content, hidden/vendored/build/test directories,
  and non-text suffixes are filtered before analysis.
- **Cheating prevention is structural.** The learner payload never contains the
  execution order (steps sorted by path; graph edges undirected). The answer key
  lives only in the server-side snapshot and is exposed solely by `/score`.
- **"Works for any repo."** The import-chain fallback is the deliberate fix for
  the earlier "only works with the ralph-wiggum repo" limitation. Framework
  request-flow detection is preferred when present; the import-chain analyzer is
  the universal fallback for arbitrary Python and JS/TS repositories.
- **Determinism via fixtures.** `LEARNING_ALLOW_FIXTURE_REPOS` (true in
  `TestingConfig`) lets tests analyze `copilot-fixtures/*` repos from disk so the
  full pipeline runs offline without GitHub access or rate limits.
- **Flow caps.** At most 4 flows, import chains at most `_MAX_CHAIN_DEPTH` deep,
  with Jaccard de-duplication to avoid presenting redundant flows.
- **Default branch.** For live repos the default branch is read from the GitHub
  API, then the archive is fetched from codeload for that branch — the analyzer
  never assumes `main`.
- **Future enhancements:** support a single non-default ref, richer flow kinds
  (e.g. CLI entrypoints, background jobs), caching of public analyses, and
  drag-to-reorder in addition to click-to-order.
