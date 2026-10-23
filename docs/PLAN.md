# Plan: strava-dashboard
Legend: [ ] todo · [~] in progress · [x] done

Before M1: the **harness** (test-architect) creates the skeleton: `pyproject.toml` + `sdash/` package with a `sdash`
entry point, `web/` (Vite + TS), ruff/mypy/pytest, eslint/prettier/tsc/vitest, Playwright, CI (`ci` + `acceptance-guard`
+ `screenshots`), a raw-data check (REQ-010), `.gitignore`, docs/TESTS.md, and acceptance tests for REQ-001…REQ-010 written
from the PRD (skipped/failing until implemented). Acceptance tests use only synthetic fixtures from T-001's generator; the
harness may add a minimal hand-made GPX fixture to get started.

The real-data spike was already done during planning (export shape + matcher feasibility, recorded in ARCHITECTURE.md).
T-001 turns it into reusable synthetic fixtures.

## M1: Pipeline end to end (export → efforts → JSON), proven on fixtures
### [ ] T-001: Synthetic fixture generator  (size S)
- Goal: `tests/fixtures/make_fixtures.py` generates a synthetic export that mirrors the real format: `activities.csv`
  with the real 101-column header (incl. duplicated names) and date format, rides as `.fit`, `.fit.gz`, `.gpx`, `.gpx.gz`,
  one sparse (~50 m spacing) ride, one Run and one Virtual Ride, one corrupt file, a `segments.csv`, a `media/` folder and
  personal files (`messages.json`, `contacts.csv`) with dummy content, zipped as `export.zip`. Tracks at made-up places,
  designed for the REQ-004 cases (normal pass, detour, reverse, two laps, out-and-back, sparse). Outputs committed.
- REQs: REQ-001, REQ-002, REQ-004 (enables their tests), REQ-010
- Acceptance tests to make pass: none directly; fixtures load in the existing acceptance tests
- Areas/files: tests/fixtures/
- Definition of done: generator + generated files committed, deterministic (re-run = no diff), a unit test checks the
  CSV header matches ARCHITECTURE.md, CI green, review clean
- Notes: FIT writing: use `fit-tool` (pip) or a minimal hand-written encoder; justify in the PR. No real data.

### [ ] T-002: Thin slice: GPX ride → one segment → JSON → segment page  (size M)
- Goal: thinnest working path: read `activities.csv`, parse GPX rides, load `segments.yaml`, simple gate matcher
  (start/end gates only), write `index.json` + `segments/<slug>.json`, and a segment page listing efforts (date, time).
  `sdash refresh --no-deploy --data-dir <dir>` runs it end to end.
- REQs: REQ-002 (GPX), REQ-003 (load), REQ-004 (basic), REQ-005, REQ-007 (table only)
- Acceptance tests to make pass: the thin-slice subset named in docs/TESTS.md (pipeline basic + segment page lists efforts)
- Areas/files: sdash/{cli,activities,tracks,segments,match,sitedata}.py, web/src/pages/segment.ts
- Definition of done: code + unit tests, listed acceptance tests pass, CI green, review clean

### [ ] T-003: All ride formats + cycling filter + cache  (size M)
- Goal: FIT, FIT.gz, GPX.gz, TCX.gz parsing; only Ride/E-Bike Ride; corrupt files reported, not fatal; per-ride cache.
- REQs: REQ-002
- Acceptance tests to make pass: tests/acceptance/pipeline/test_parse*.py
- Areas/files: sdash/tracks.py, sdash/activities.py
- Definition of done: code + unit tests, listed acceptance tests pass, CI green, review clean

### [ ] T-004: Import from local zip and https link (safe extraction)  (size M)
- Goal: `sdash import <zip|url>`: allowlist extraction, zip-slip/abs-path/size-cap rejection, https + host allowlist,
  link never logged, zip deleted after import, old ride files replaced.
- REQs: REQ-001
- Acceptance tests to make pass: tests/acceptance/pipeline/test_import*.py (URL tests use a local https test server or
  a mocked transport, never the network)
- Areas/files: sdash/importer.py, sdash/cli.py
- Definition of done: code + unit tests, listed acceptance tests pass, CI green, review clean
- Notes: security-relevant. The reviewer checks the extraction and URL handling explicitly.

### [ ] T-005: Full matcher rules  (size M)
- Goal: REQ-004 in full: length ±10 %, path check against every ride point, direction, multiple laps, out-and-back,
  sparse tracks, non-ride reference activity.
- REQs: REQ-004
- Acceptance tests to make pass: tests/acceptance/pipeline/test_match*.py
- Areas/files: sdash/match.py
- Definition of done: code + unit tests, listed acceptance tests pass, CI green, review clean

### [ ] T-006: Segment file validation, `segment add`, `segment import-strava`  (size S)
- Goal: validate segments.yaml (REQ-003 errors), add a segment from ride + km range, import Strava `segments.csv`.
- REQs: REQ-003
- Acceptance tests to make pass: tests/acceptance/pipeline/test_segments*.py
- Areas/files: sdash/segments.py, sdash/cli.py
- Definition of done: code + unit tests, listed acceptance tests pass, CI green, review clean

## M2: The site (index, segment, ride pages)
All M2 UI tasks follow docs/DESIGN.md (tokens, type, layout, screens) and the reference mockups in docs/design/.
Milestone review compares the screenshots with those mockups.
### [ ] T-007: Site data complete: ranks, PR at the time, averages, per-year, determinism  (size M)
- Goal: full JSON schema from ARCHITECTURE.md, byte-identical rebuilds, no coordinates.
- REQs: REQ-005
- Acceptance tests to make pass: tests/acceptance/pipeline/test_sitedata*.py
- Areas/files: sdash/sitedata.py
- Definition of done: code + unit tests, listed acceptance tests pass, CI green, review clean

### [ ] T-008: Base layout + design tokens + Index page  (size M)
- Goal: `tokens.css` and base styles from docs/DESIGN.md, self-hosted Public Sans, header/nav, panel and table
  components, not-found route; then the Index page (segment list + ride list, links, empty state). T-002's segment page
  adopts the base layout.
- REQs: REQ-006
- Acceptance tests to make pass: tests/acceptance/web/index.spec.ts
- Areas/files: web/src/styles/, web/public/fonts/, web/src/pages/index.ts, web/src/lib/
- Definition of done: code + unit tests, listed acceptance tests pass, CI green, review clean

### [ ] T-009: Segment page complete: ranks, gap to PR, sorting, per-year, trend chart  (size M)
- Goal: REQ-007 in full with Chart.js, matching docs/design/segment-page.dc.html.
- REQs: REQ-007
- Acceptance tests to make pass: tests/acceptance/web/segment.spec.ts
- Areas/files: web/src/pages/segment.ts
- Definition of done: code + unit tests, listed acceptance tests pass, CI green, review clean

### [ ] T-010: Ride page  (size M)
- Goal: ride summary + matched efforts vs PR/average with the position bar, PR-at-the-time marking, empty state,
  matching docs/design/ride-page.dc.html.
- REQs: REQ-008
- Acceptance tests to make pass: tests/acceptance/web/ride.spec.ts
- Areas/files: web/src/pages/ride.ts
- Definition of done: code + unit tests, listed acceptance tests pass, CI green, review clean

## M3: One-command refresh and deploy
### [ ] T-011: `sdash refresh` full chain + output guard + report  (size M)
- Goal: import → parse → match → build-data → `npm run build` → guard; stops on any failure; report with rides parsed,
  failures, efforts per segment; `--no-deploy`; segments.yaml backups (D-004).
- REQs: REQ-009, REQ-010
- Acceptance tests to make pass: tests/acceptance/pipeline/test_refresh*.py
- Areas/files: sdash/cli.py, sdash/deploy.py (guard part)
- Definition of done: code + unit tests, listed acceptance tests pass, CI green, review clean

### [ ] T-012: `sdash deploy` to gh-pages  (size S)
- Goal: commit `web/dist` to the `gh-pages` branch through a git worktree and push (normal push, never force, never main);
  `--remote` configurable so tests push to a local bare repo.
- REQs: REQ-009
- Acceptance tests to make pass: tests/acceptance/pipeline/test_deploy*.py (local bare repo only)
- Areas/files: sdash/deploy.py, docs/DEPLOY.md
- Definition of done: code + unit tests, listed acceptance tests pass, CI green, review clean. The first real deploy
  happens in the deploy phase, not in this task.

## Screens (web UI projects)
Captured from the fixture-built site.
- Index: with segments and rides · no segments defined (empty state)
- Segment: with efforts (table + chart, PR highlighted) · sorted by date · no efforts
- Ride: with matched efforts (incl. a PR) · no matched segments
- Unknown route (`#/segment/does-not-exist`): not-found message
