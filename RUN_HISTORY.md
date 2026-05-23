# Run history (v1.1)

Internal spec for persisting and browsing past PDP lab runs. Supersedes the MVP constraint of “no long-term run history” from the original product plan.

## Goal

Let operators **list, reopen, and compare past runs** (especially incomplete ones) without re-running SerpAPI, Firecrawl, or LLM steps.

**Out of scope for v1.1:** async job queue, prompt versioning, bulk replay, CMS export, full-text search, multi-user run isolation, “re-run with these settings.”

## Background

- Runs are **synchronous HTTP** (`POST /lab/run-with-upload`), not background jobs. UI copy should say **Run history**, not “job queue.”
- `RunResult` already carries status, sources, step outputs, cost/runtime, `audit`, and `internal_report_html`.
- SQLite + SQLModel exist for settings and config; runs are currently returned and discarded.

## Data model

### Table: `LabRun`

| Column | Type | Notes |
|--------|------|--------|
| `id` | int, PK | Auto-increment |
| `created_at` | datetime (UTC) | Indexed, default now |
| `manufacturer_name` | str | Denormalized for list |
| `manufacturer_product_number` | str | Denormalized for list |
| `status` | str | `complete` \| `incomplete` |
| `match_verified` | bool | |
| `incomplete_reason` | str \| null | Truncate to ~500 chars for list display |
| `total_cost_usd` | float | |
| `total_runtime_ms` | int | |
| `style_guide_filename` | str | Empty if none |
| `style_guide_hash` | str \| null | SHA-256 of uploaded guide bytes; omit full text |
| `result_json` | JSON | Full `RunResult.model_dump()` |

**Do not store separately:** duplicate `internal_report_html` if it can be regenerated from `result_json` via `render_internal_report` (optional: keep HTML inside JSON only).

**Omit from persistence by default:** full style guide text, raw scraped markdown in `audit` if present (cap or strip in `save_run` if blobs grow too large).

### Retention

Configurable via env (defaults in parentheses):

| Setting | Default | Behavior |
|---------|---------|----------|
| `RUN_HISTORY_MAX_COUNT` | `100` | After each save, delete oldest rows beyond cap |
| `RUN_HISTORY_MAX_AGE_DAYS` | `30` | Delete rows older than N days (0 = disabled) |

Prune on **startup** and after **each save** (keep logic simple).

## API

All routes require the same auth as existing `/lab/*` endpoints.

| Method | Path | Response |
|--------|------|----------|
| `POST` | `/lab/run-with-upload` | Unchanged body; **also** persists run after orchestrator returns |
| `POST` | `/lab/run` | Same persistence hook |
| `GET` | `/lab/runs` | `?limit=50&offset=0` → list of summaries |
| `GET` | `/lab/runs/{id}` | Full `RunResult` from `result_json` |
| `DELETE` | `/lab/runs/{id}` | Optional; remove one run |

### Summary schema (`RunSummary`)

```json
{
  "id": 1,
  "created_at": "2026-05-23T12:00:00Z",
  "manufacturer_name": "...",
  "manufacturer_product_number": "...",
  "status": "incomplete",
  "match_verified": false,
  "incomplete_reason": "Incomplete: ...",
  "total_cost_usd": 0.0421,
  "total_runtime_ms": 95000,
  "style_guide_filename": "guide.md"
}
```

Detail endpoint returns the stored `RunResult` shape (same as live run response).

## Backend implementation

### Files (planned)

| File | Responsibility |
|------|----------------|
| `backend/app/models/db.py` | Add `LabRun` SQLModel table |
| `backend/app/models/schemas.py` | `RunSummary`, list response wrapper |
| `backend/app/repositories/run_history.py` | `save_run`, `list_runs`, `get_run`, `prune_runs` |
| `backend/app/api/lab.py` | Persistence after `execute_run_safe`; new GET/DELETE routes |
| `backend/app/config.py` | `run_history_max_count`, `run_history_max_age_days` |
| `backend/app/main.py` | Call `prune_runs` on startup (after `init_db`) |

### Save hook

1. Orchestrator returns `RunResult` (unchanged).
2. Route layer calls `save_run(result, request_metadata)`:
   - Copy summary fields from `RunResult` + request manufacturer/MPN/filename.
   - Hash style guide if uploaded (from request bytes, not settings table).
   - Serialize `result_json`.
   - Run retention prune.

Failures to save must **not** fail the HTTP run response (log warning only).

## Frontend implementation

### Files (planned)

| File | Responsibility |
|------|----------------|
| `frontend/src/api/client.ts` | `RunSummary`, `listRuns`, `getRun` |
| `frontend/src/components/RunHistory.tsx` | Sidebar or section: table of recent runs |
| `frontend/src/pages/Lab.tsx` | Load selected run into `RunResults`; highlight incomplete |
| `frontend/src/components/RunResults.tsx` | Optionally show sources / step outputs when present |

### UX

- **Recent runs** list: manufacturer, MPN, status pill, cost, relative time.
- Click row → fetch `GET /lab/runs/{id}` → populate `RunResults` (same as post-run view).
- **Download internal report** uses `internal_report_html` from detail payload.
- Active run still replaces view on new submit; history selection is read-only.

## Operations (Railway)

- Mount a **volume** at the backend working directory so `lab.db` survives redeploys.
- Document `RUN_HISTORY_*` vars in `backend/.env.example`.
- Monitor DB size; retention defaults target ~100 runs × ~few hundred KB each.

## Privacy

- Single shared login today → no per-user filtering.
- Do not persist full style guide text in `LabRun` rows (filename + hash only).

## Implementation order

1. `LabRun` model + migration via `create_all` + `save_run` hook on run endpoints.
2. `GET /lab/runs` and `GET /lab/runs/{id}`.
3. Retention prune (startup + post-save).
4. Frontend list + detail (reuse `RunResults`).
5. Railway volume + `.env.example` documentation.

## Acceptance criteria

- [x] Completing or incompleting a run creates a `LabRun` row visible in `GET /lab/runs`.
- [x] Opening a past run shows the same result UI as a fresh run (status, content, cost, runtime, report download).
- [x] Retention enforces max count and/or max age without manual DB edits.
- [x] Save failures do not break `POST /lab/run-with-upload`.
- [ ] History survives backend restart when SQLite file is on persistent disk (requires Railway volume in production).

## Future (not v1.1)

- Re-run with settings from a stored run
- Compare two runs side-by-side
- Filter/search by MPN or status
- Async runs + job status if bulk processing is added
