# strava-dashboard
Follows Martin's framework: ~/.claude/FRAMEWORK.md (skills: plan, harness, next-task, deploy).
State: docs/STATUS.md (read it first). Plan: docs/PRD.md, docs/ARCHITECTURE.md, docs/PLAN.md. Tests: docs/TESTS.md.

## Stack
- Pipeline: Python 3.12 package `sdash/` (CLI `sdash`), fitdecode, gpxpy, PyYAML; ruff, mypy (strict on sdash/), pytest.
- Site: `web/` Vite + TypeScript (no framework), Chart.js, hash routing, base `/strava-dashboard/`; eslint, prettier,
  tsc, vitest, Playwright. Node 24 + npm (`web/package-lock.json`).
- Details: docs/ARCHITECTURE.md. UI spec: docs/DESIGN.md. Test map and contracts: docs/TESTS.md.

## Commands (from the repo root)
- Install: `python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'` · `npm --prefix web ci` ·
  once per machine: `cd web && npx playwright install chromium`
- Run: `.venv/bin/sdash --help` (data dir: `--data-dir DIR` or `$SDASH_DATA_DIR`, default `~/data/strava-export`) ·
  site dev server: `npm --prefix web run dev` · built preview: `npm --prefix web run build && npm --prefix web run preview`
- Lint / format / typecheck: `.venv/bin/ruff check .` · `.venv/bin/ruff format --check .` · `.venv/bin/mypy` ·
  `npm --prefix web run lint` · `npm --prefix web run format:check` · `npm --prefix web run typecheck`
  (auto-format: `.venv/bin/ruff format .` · `npm --prefix web run format`)
- Unit tests: `.venv/bin/pytest tests/unit` · `npm --prefix web test`
- Acceptance tests: `.venv/bin/pytest tests/acceptance/pipeline` · `npm --prefix web run test:acceptance`
  (copies tests/fixtures/site-data into web/public/data, builds, runs Playwright on port 4318)
- Run not-yet-implemented acceptance tests anyway: `.venv/bin/pytest --runxfail ...` · `ACCEPTANCE_RUN_ALL=1 npm --prefix web run test:acceptance`
- Raw-data check (REQ-010): `python3 scripts/check_raw_data.py`
- Screenshots: `npm --prefix web run screenshots` → `screenshots/`
- The VPS has 4 GB RAM: run one test level at a time; mutation testing runs only in CI.

## Conventions
- Acceptance tests (tests/acceptance/) are written from the PRD and are protected (acceptance-guard). Not yet
  implemented = pytest `@pytest.mark.xfail(strict=True, reason="REQ-00x not implemented (T-00y)")` or Playwright
  `fixme(...)` (helpers.ts). The task that makes a test pass removes its marker (`fixme(` → `test(`) in the same PR;
  strict xfail turns an unexpected pass into a CI failure. Never weaken or delete an acceptance test to get green.
- Test names carry the REQ ID (`test_req004_...`, `"REQ-007: ..."` + tag `@REQ-007`); docs/TESTS.md maps REQ → tests
  and documents the CLI/UI contracts the tests rely on.
- All test data is synthetic: generated tracks in the made-up area lat −48…−46, lon −136…−133 (open ocean), made-up
  names and IDs. Never read or copy anything from `~/data/strava-export/` into the repo or tests.
- Raw ride/export files (`*.fit`, `*.gpx`, `*.tcx`, `*.zip`, `activities.csv`, + `.gz`) are allowed only under
  tests/fixtures/ (.gitignore + CI check). The site never contains coordinates.
- Tests never use the network: URL imports use a local HTTPS server, deploys push to a local bare repo.
- Python: type hints everywhere in `sdash/` (mypy strict). Web: no innerHTML with data; use `web/src/lib/dom.ts`.
