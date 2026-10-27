# Plan: strava-dashboard
Legend: [ ] todo · [~] in progress · [x] done

Before M1: the **harness** (test-architect) creates the skeleton: `pyproject.toml` + `sdash/` package with a `sdash`
entry point, `web/` (Vite + TS), ruff/mypy/pytest, eslint/prettier/tsc/vitest, Playwright, CI (`ci` + `acceptance-guard`
+ `screenshots`), a raw-data check (REQ-010), `.gitignore`, docs/TESTS.md, and acceptance tests for REQ-001…REQ-010 written
from the PRD (skipped/failing until implemented). Acceptance tests use only synthetic inputs (built by the harness in
`tests/acceptance/pipeline/_synth.py` and `tests/acceptance/web/make_site_data.py`).

The real-data spike was already done during planning (export shape + matcher feasibility, recorded in ARCHITECTURE.md).
T-001 aligns the synthetic export with the recorded real header (Plan v2).

## M1: Pipeline end to end (export → efforts → JSON), proven on fixtures
### [x] T-001: Align synthetic activities.csv header with the real export  (size S)
- Goal: `_synth.ACTIVITIES_HEADER` equals the exact 103-column header recorded in docs/ARCHITECTURE.md (harness used 99
  publicly documented names). A unit test parses the header block from ARCHITECTURE.md and compares it with
  `ACTIVITIES_HEADER`. Duplicate-column handling (first occurrence wins) still holds.
- REQs: REQ-002, REQ-010
- Acceptance tests to make pass: none newly; all currently passing acceptance tests stay passing, xfails stay xfail.
- Areas/files: tests/acceptance/pipeline/_synth.py (**explicitly allowed acceptance change**: header list only; needs
  test-reviewer), tests/unit/
- Definition of done: header matches, unit test added, CI green, review + test-review clean
- Notes: column names only come from ARCHITECTURE.md; never read ~/data.

### [x] T-002: Thin slice: GPX ride → one segment → JSON → segment page  (size M)
- Goal: thinnest working path: read `activities.csv`, parse GPX rides, load `segments.yaml`, simple gate matcher
  (start/end gates only), write `index.json` + `segments/<slug>.json`, and a segment page listing efforts (date, time).
  `sdash refresh --no-deploy --data-dir <dir>` runs it end to end.
- REQs: REQ-002 (GPX), REQ-003 (load), REQ-004 (basic), REQ-005, REQ-007 (table only)
- Acceptance tests to make pass: the thin-slice subset named in docs/TESTS.md (pipeline basic + segment page lists efforts)
- Areas/files: sdash/{cli,activities,tracks,segments,match,sitedata}.py, web/src/pages/segment.ts
- Definition of done: code + unit tests, listed acceptance tests pass, CI green, review clean

### [x] T-003: All ride formats + cycling filter + cache  (size M)
- Goal: FIT, FIT.gz, GPX.gz, TCX.gz parsing; only Ride/E-Bike Ride; corrupt files reported, not fatal; per-ride cache.
- REQs: REQ-002
- Acceptance tests to make pass: tests/acceptance/pipeline/test_parse*.py
- Areas/files: sdash/tracks.py, sdash/activities.py
- Definition of done: code + unit tests, listed acceptance tests pass, CI green, review clean

### [x] T-004: Import from local zip and https link (safe extraction)  (size M)
- Goal: `sdash import <zip|url>`: allowlist extraction, zip-slip/abs-path/size-cap rejection, https + host allowlist,
  link never logged, zip deleted after import, old ride files replaced.
- REQs: REQ-001
- Acceptance tests to make pass: tests/acceptance/pipeline/test_import*.py (URL tests use a local https test server or
  a mocked transport, never the network)
- Also: unit tests for host matching: `evilstrava.com` must not match `strava.com`; allowlist `calhost` must not match
  host `localhost`.
- Areas/files: sdash/importer.py, sdash/cli.py
- Definition of done: code + unit tests, listed acceptance tests pass, CI green, review clean
- Notes: security-relevant. The reviewer checks the extraction and URL handling explicitly.

### [x] T-005: Full matcher rules  (size M)
- Goal: REQ-004 in full: length ±10 %, path check against every ride point, direction, multiple laps, out-and-back,
  sparse tracks, non-ride reference activity.
- REQs: REQ-004
- Acceptance tests to make pass: tests/acceptance/pipeline/test_match*.py
- Areas/files: sdash/match.py
- Definition of done: code + unit tests, listed acceptance tests pass, CI green, review clean

### [x] T-006: Segment file validation, `segment add`, `segment import-strava`  (size S)
- Goal: validate segments.yaml (REQ-003 errors), add a segment from ride + km range, import Strava `segments.csv`.
- REQs: REQ-003
- Acceptance tests to make pass: tests/acceptance/pipeline/test_segments*.py
- Areas/files: sdash/segments.py, sdash/cli.py
- Definition of done: code + unit tests, listed acceptance tests pass, CI green, review clean

## M2: The site (index, segment, ride pages)
M2 starts with three fix tasks from the M1 review (Plan v3), then the site tasks.

### [x] T-013: Real-data fixes from the M1 check  (size M)
- Goal: (1) activities.csv numbers with thousands separators read correctly in all rows; reference-track lookup reports
  read errors instead of swallowing them. (2) Out-and-back reference: skip gate pairs shorter than a minimum (e.g.
  2 × gate = 60 m ridden distance) and use the next end pass. (3) Segment-level problems (invalid fields, duplicate
  name: keep the first, skip the next; missing/unusable reference) are reported and skipped; other segments are
  matched and built; `match`/`build-data`/`refresh` exit 2; `refresh` still deploys. Unreadable segments.yaml stays a
  hard failure. (4) TCX with text/whitespace/BOM before the XML declaration parses.
- REQs: REQ-002, REQ-003, REQ-004, REQ-009 (Plan v3 criteria)
- Acceptance tests to make pass: new tests for the Plan v3 criteria. **Explicitly allowed acceptance changes** (need
  test-reviewer): add tests for the new criteria to tests/acceptance/pipeline/ (thousands-separator row, TCX with
  leading text, jittery out-and-back reference, one bad segment + one good segment -> exit 2 and the good one built);
  change test_refresh.py `test_req009_any_failed_step_deploys_nothing[invalid-segments]` to the new rule (invalid
  segment next to a valid one -> exit 2, valid segment deployed, warning names the bad segment) and add an
  unreadable-YAML case that still deploys nothing. No other acceptance edits.
- Areas/files: sdash/activities.py, sdash/tracks.py, sdash/match.py, sdash/pipeline.py, sdash/cli.py, docs/TESTS.md
  (contracts: exit code 2), tests
- Definition of done: code + unit tests, listed acceptance tests pass, CI green, review + test-review clean; Lead
  re-runs the private real-data check: Sitno hike segments get a reference, the otočka segment matches, 662/662 parsed.

### [x] T-014: Hardening leftovers from M1 reviews  (size S)
- Goal: FIT failure reasons include the exception type; cache `_num_list` rejects Infinity; drop dead GPX
  `latitude is None` check (test: lat-less trkpt -> reported failure); DTD test `match="DTD"` + UTF-32 case; drop the
  vacuous `except ValueError: return` in the fuzz test; huge YAML integers -> clear error (catch ValueError in
  load_segments); importer: name the entry on file/dir clash, cap entry count (e.g. 100 000), overall download
  deadline, chmod existing data dir 0700, clean stale .raw-old-*/.raw-staging-*/.download-* on start; `is_reference`
  via a set of IDs; note in ARCHITECTURE that proxies are ignored.
- REQs: REQ-001, REQ-002, REQ-003 (robustness)
- Acceptance tests to make pass: none newly; all stay green
- Areas/files: sdash/, tests/unit/, docs/ARCHITECTURE.md (proxy note only)
- Definition of done: code + unit tests, CI green, review clean

### [x] T-015: CI fixes: mutation workflow and Playwright install time  (size S)
- Goal: mutation.yml + mutmut config produce a real score on sdash/match.py (verify locally that mutants are actually
  run; current run: 488 mutants all "not checked" because of deprecated config keys); speed up "Install Playwright
  browser" (Playwright container image or cached browsers + deps), keeping the `ci` job name and steps.
- REQs: – (test infrastructure)
- Acceptance tests to make pass: none; all stay green
- Areas/files: **explicitly allowed workflow change**: .github/workflows/mutation.yml, .github/workflows/ci.yml,
  .github/workflows/screenshots.yml, pyproject.toml (mutmut config). Never acceptance-guard.yml. Needs test-reviewer
  (and Martin's `acceptance-change` label if the guard requires it).
- Definition of done: mutation run on a test branch shows killed/survived counts; ci install step < 2 min on a cold
  run; CI green, review + test-review clean

All M2 UI tasks follow docs/DESIGN.md (tokens, type, layout, screens) and the reference mockups in docs/design/.
Milestone review compares the screenshots with those mockups.
### [x] T-007: Site data complete: ranks, PR at the time, averages, per-year, determinism  (size M)
- Goal: full JSON schema from ARCHITECTURE.md, byte-identical rebuilds, no coordinates.
- REQs: REQ-005
- Acceptance tests to make pass: tests/acceptance/pipeline/test_sitedata*.py
- Areas/files: sdash/sitedata.py
- Definition of done: code + unit tests, listed acceptance tests pass, CI green, review clean

### [x] T-008: Base layout + design tokens + Index page  (size M)
- Goal: `tokens.css` and base styles from docs/DESIGN.md, self-hosted Public Sans, header/nav, panel and table
  components, not-found route; then the Index page (segment list + ride list, links, empty state). T-002's segment page
  adopts the base layout.
- REQs: REQ-006
- Acceptance tests to make pass: tests/acceptance/web/index.spec.ts
- Areas/files: web/src/styles/, web/public/fonts/, web/src/pages/index.ts, web/src/lib/
- Notes: exactly one link per ride row (index.spec uses a strict `getByRole("link")`).
- Definition of done: code + unit tests, listed acceptance tests pass, CI green, review clean

### [x] T-009: Segment page complete: ranks, gap to PR, sorting, per-year, trend chart  (size M)
- Goal: REQ-007 in full with Chart.js, matching docs/design/segment-page.dc.html.
- REQs: REQ-007
- Acceptance tests to make pass: tests/acceptance/web/segment.spec.ts
- Areas/files: web/src/pages/segment.ts
- Definition of done: code + unit tests, listed acceptance tests pass, CI green, review clean

### [x] T-010: Ride page  (size M)
- Goal: ride summary + matched efforts vs PR/average with the position bar, PR-at-the-time marking, empty state,
  matching docs/design/ride-page.dc.html. Dates/times in Europe/Bratislava (D-007).
- Also: **explicitly allowed acceptance change**: add the REQ-008 time-zone criterion test to
  tests/acceptance/web/ride.spec.ts (+ a summer 15:05Z ride in make_site_data.py if none exists); needs test-reviewer.
- REQs: REQ-008
- Acceptance tests to make pass: tests/acceptance/web/ride.spec.ts
- Areas/files: web/src/pages/ride.ts
- Definition of done: code + unit tests, listed acceptance tests pass, CI green, review clean

## M3: One-command refresh and deploy
M3 starts with the M2 review fixes (Plan v4), then the refresh/deploy tasks.

### [x] T-016: Segment chart: correct dot positions + capped time axis  (size M)
- Goal: (1) fix the M2 real-data bug: on a segment with efforts over ~3 years (Oct 2019 – May 2021) the effort dots are
  drawn squeezed toward the start of the time axis (and keep moving after load), while the "PR m:ss" label is at the
  correct date; dots must be at their actual dates. Reproduce first with a synthetic segment of that shape. (2) Cap the
  y axis at about 2× the median elapsed time; efforts beyond it are triangle markers on the slow edge at their date; the
  panel header says "N slower efforts above the cap"; the canvas aria-label mentions it.
- REQs: REQ-007 (Plan v4 criteria)
- Acceptance tests to make pass: **explicitly allowed acceptance change** (needs test-reviewer): add to
  tests/acceptance/web/make_site_data.py one synthetic segment spanning ~3 years with one effort > 2× median (+ its
  rides), regenerate site-data deterministically, and add segment.spec.ts tests: (a) the PR dot is drawn within the
  horizontal band of its date's year (pixel check between year gridlines or via an exposed chart-model attribute),
  (b) the header/aria-label state the number of efforts above the cap. No other acceptance edits.
- Areas/files: web/src/lib/segment-chart.ts, web/src/lib/segment-data.ts, web/src/pages/segment.ts, tests
- Definition of done: code + unit tests, listed acceptance tests pass, CI green, review + test-review clean; Lead
  re-checks the real-data segment page privately.

### [x] T-017: Ride page: median instead of average, position bar PR -> slowest  (size M)
- Goal: site data adds `median_s` and `slowest_s` per effort in rides/<id>.json (sdash/sitedata.py, ARCHITECTURE
  definitions); the ride page shows "Median" instead of "Average", the bar runs from PR to slowest with a median tick,
  legend "bar: PR on the left, slowest on the right · | median · ● today".
- REQs: REQ-008, REQ-005
- Acceptance tests to make pass: **explicitly allowed acceptance change** (needs test-reviewer): make_site_data.py adds
  `median_s` and `slowest_s` (same definitions as ARCHITECTURE), regenerate site-data; in ride.spec.ts the test
  "REQ-008: each matched effort shows time, PR, average, gap to PR and rank" becomes "…median…" with the median values
  instead of the average values (same rows, same other assertions). No other acceptance edits.
- Areas/files: sdash/sitedata.py, docs/ARCHITECTURE.md, web/src/pages/ride.ts, web/src/lib/ride-data.ts, tests
- Definition of done: code + unit tests, listed acceptance tests pass, CI green, review + test-review clean

### [x] T-018: Matcher tests for surviving mutants  (size S)
- Goal: targeted unit tests that kill the M2 mutation survivors in sdash/match.py (91 survived of 498; mostly
  `reference_from` 23, `find_efforts` 19, `distance_to_polyline_m` 13); no production behaviour change unless a test
  exposes a real bug (then fix + note). Target: mutation score ≥ 90 % in the next milestone run.
- REQs: REQ-004
- Acceptance tests to make pass: none newly; all stay green
- Areas/files: tests/unit/test_match.py (+ sdash/match.py only for real bugs)
- Definition of done: unit tests, local mutmut run on the targeted functions at low parallelism (or a CI dispatch of
  the mutation workflow) shows the survivors killed; CI green, review clean

### [x] T-011: `sdash refresh` full chain + output guard + report  (size M)
- Goal: import → parse → match → build-data → `npm run build` → guard; stops on any failure; report with rides parsed,
  failures, efforts per segment; `--no-deploy`; segments.yaml backups (D-004).
- REQs: REQ-009, REQ-010
- Acceptance tests to make pass: tests/acceptance/pipeline/test_refresh*.py
- Areas/files: sdash/cli.py, sdash/deploy.py (guard part)
- Definition of done: code + unit tests, listed acceptance tests pass, CI green, review clean

### [x] T-012: `sdash deploy` to gh-pages  (size S)
- Goal: commit `web/dist` to the `gh-pages` branch through a git worktree and push (normal push, never force, never main);
  `--remote` configurable so tests push to a local bare repo.
- REQs: REQ-009
- Acceptance tests to make pass: tests/acceptance/pipeline/test_deploy*.py (local bare repo only)
- Areas/files: sdash/deploy.py, docs/DEPLOY.md, web/ (`npm run smoke -- --base <url>`: Playwright smoke against a live
  URL used by DEPLOY.md: index, one segment page, one ride page load without errors)
- Definition of done: code + unit tests, listed acceptance tests pass, CI green, review clean. The first real deploy
  happens in the deploy phase, not in this task.

## Screens (web UI projects)
Captured from the fixture-built site.
- Index: with segments and rides · no segments defined (empty state)
- Segment: with efforts (table + chart, PR highlighted) · sorted by date · no efforts
- Ride: with matched efforts (incl. a PR) · no matched segments
- Unknown route (`#/segment/does-not-exist`): not-found message
