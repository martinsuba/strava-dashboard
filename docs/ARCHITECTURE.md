# Architecture: strava-dashboard

## Overview
A Python CLI (`sdash`) on agent-vps turns a Strava account export into derived JSON. A small static frontend
(Vite + TypeScript) renders that JSON. The built site is pushed to the `gh-pages` branch and served by GitHub Pages at
`https://martinsuba.github.io/strava-dashboard/`. No server runs at request time.

```
export link / zip
      │  sdash import          (download https, safe-extract ride files only, delete the rest)
      ▼
~/data/strava-export/raw/      activities.csv, activities/*.fit(.gz)|gpx(.gz)|tcx.gz, segments.csv
      │  sdash parse           (cycling only, cached per activity)
      ▼
~/data/strava-export/cache/    one normalised track per ride (time, lat, lon, cum. distance)
      │  sdash match  ◄──────── ~/data/strava-export/segments.yaml
      ▼
web/public/data/ (gitignored)  index.json, segments/<slug>.json, rides/<id>.json   (no coordinates)
      │  npm run build
      ▼
web/dist/  ──guard──► sdash deploy ──► gh-pages branch ──► GitHub Pages
```

## Stack (language, framework, DB, test tools) and why
- **Pipeline: Python 3.12**, `fitdecode` (FIT), `gpxpy` (GPX), stdlib `csv`, `zipfile`, `gzip`, `urllib`/`httpx`, `PyYAML`.
  Python has the most mature FIT tooling; the spike parsed every ride in the export with these two libraries.
  Packaging: `pyproject.toml`, plain `venv` + `pip install -e .[dev]` (no uv on the VPS).
  Quality: `ruff` (lint + format), `mypy` (strict on `sdash/`), `pytest`.
- **Frontend: Vite + TypeScript, no framework** (three read-only pages), `Chart.js` for charts, hash routing
  (`#/segment/<slug>`, `#/ride/<id>`) so GitHub Pages needs no 404 tricks. Vite `base: '/strava-dashboard/'`.
  Quality: `eslint`, `prettier`, `tsc --noEmit`, `vitest` for formatting/helpers.
- **Acceptance tests:** `pytest` running the `sdash` CLI as a subprocess on synthetic fixtures (tests/acceptance/pipeline/),
  and Playwright against the site built from fixture data (tests/acceptance/web/).
- **Mutation testing:** `mutmut` on `sdash/match.py` (critical logic), milestone PRs only, report only.
- No database: files are the store; the data is small (~150 MB raw, a few MB derived).

## Components and responsibilities
| Component | Path | Responsibility |
|---|---|---|
| CLI | `sdash/cli.py` | subcommands `import`, `parse`, `match`, `build-data`, `segment add`, `segment import-strava`, `deploy`, `refresh` |
| Import | `sdash/importer.py` | https download (allowed hosts, size cap), safe zip extraction with allowlist, delete zip |
| Activities | `sdash/activities.py` | read `activities.csv` (duplicate headers, date format), filter cycling |
| Parsers | `sdash/tracks.py` | FIT / GPX / TCX (+ .gz) → `Track` (t, lat, lon, cumdist); cache read/write |
| Segments | `sdash/segments.py` | load/validate `segments.yaml`, slug, `add` from ride + km, import from Strava `segments.csv` |
| Matcher | `sdash/match.py` | find efforts (rules in REQ-004) |
| Site data | `sdash/sitedata.py` | ranks, PR-at-the-time, averages, per-year stats → JSON; deterministic |
| Deploy | `sdash/deploy.py` | output guard, commit `web/dist` to `gh-pages` via a git worktree, push |
| Web | `web/` | `index.html`, `src/pages/{index,segment,ride}.ts`, `src/lib/format.ts` |

Data dir: `SDASH_DATA_DIR`, default `~/data/strava-export/` (`raw/`, `cache/`, `segments.yaml`, `reports/`).

## Data model
- **Activity** (from `activities.csv`): `id` (str), `date` (UTC ISO 8601), `name`, `type`, `gear`, `distance_km`,
  `elapsed_s`, `moving_s`, `filename`.
- **Track**: arrays `t` (epoch s), `lat`, `lon`, `d` (cumulative m). Cache: `cache/<id>.json.gz`, keyed by file size + mtime.
- **Segment** (`segments.yaml`):
  ```yaml
  - name: River path north        # synthetic example
    ref_activity: "1000000001"
    start: [45.100000, 10.200000]
    end: [45.150000, 10.180000]
  ```
  Derived: `slug`, `ref_length_m`, `ref_points` (reference track sampled every ~50 m).
- **Effort**: `segment_slug`, `activity_id`, `start_t`, `elapsed_s`, `distance_m`, `avg_kmh`, `rank`, `gap_to_pr_s`,
  `is_pr_at_time`.
- **Site JSON**:
  - `index.json`: `{generated, segments: [{slug, name, efforts, pr_s, pr_date}], rides: [{id, date, name, km, n_efforts}]}`
  - `segments/<slug>.json`: `{name, ref_length_m, efforts: [...], per_year: [{year, count, best_s}]}`
  - `rides/<id>.json`: `{id, date, name, km, elapsed_s, moving_s, gear, efforts: [{slug, name, elapsed_s, pr_s, avg_s, gap_to_pr_s, rank, of, is_pr, is_pr_at_time}]}`

## External services / APIs

### Strava account export (verified 2026-10-23 with Martin's real export)
- Delivered as an email link `https://email.strava.com/ls/click?...`, which redirects once (https) to a pre-signed
  `https://s3.amazonaws.com/...` URL; `Content-Type: application/zip`. Today's size: 549 MB zip, 666 MB unpacked, 2,441 entries.
- Top level: `activities.csv`, `activities/` (1,674 files, 156 MB), `media/` (725 files, 509 MB) and ~40 personal CSV/JSON
  files (messages, contacts, logins, followers, profile…), plus `segments.csv`, `starred_segments.csv`, `bikes.csv`, `routes/`.
  No unsafe paths were present, but the importer must still check.
- Extraction allowlist: `activities.csv`, `activities/`, `segments.csv`, `starred_segments.csv`, `bikes.csv`, `components.csv`.
- `activities.csv`: 1,714 rows, 101 columns, **duplicated headers** (`Elapsed Time`, `Distance`, `Max Heart Rate`,
  `Relative Effort`, `Commute` appear twice; first occurrence = the summary values). `Activity Date` like
  `Oct 20, 2026, 3:45:46 AM` (UTC). `Filename` like `activities/<file-id>.fit.gz` (file ID ≠ activity ID).
  Types: Ride 661, Run 467, Weight Training 366, Walk 95, Hike 77, Virtual Ride 20, E-Bike Ride 1, …
- Ride files (662): `fit.gz` 552, `fit` 10, `gpx` 119, `tcx.gz` 1. All present.
  - FIT from Lezyne Mega XL (2024+): `record` with timestamp, position_lat/long (semicircles, × 180/2³¹), altitude,
    distance, speed, temperature, sometimes heart_rate. fitdecode warns about developer fields; harmless.
  - FIT from Garmin FR735XT (2019–2023): same, plus accumulated_power; often "smart recording" (≈ one point per 50 m).
  - GPX (creator `StravaGPX`, 2016–2019): trkpt with time and elevation, no extensions.
  - No file contains segment or lap-segment messages.
- `segments.csv`: `Segment Name, Activity ID, Starting Latitude, Starting Longitude, Ending Latitude, Ending Longitude`
  (5 rows; 3 cycling segments in Prague, 2 drawn on a hike). `starred_segments.csv`: date + Strava segment ID only (unusable).
- Fixtures: synthetic only (T-001), mirroring these formats at made-up coordinates.

### Spike result: matcher feasibility (2026-10-23, throwaway script)
Parsing all rides took 146 s. With the REQ-004 rules, the 3 Prague segments matched 26, 32 and 12 efforts; the best was
~31–33 km/h, which is plausible. Lessons: never subsample the ride when checking the path (sparse tracks fail); the
reference activity may be a non-ride.

### GitHub Pages
Served from the `gh-pages` branch root. Requires a public repo on Martin's plan. URL `https://martinsuba.github.io/strava-dashboard/`.

## Security & privacy notes
- The export link is a credential for the whole account archive: pass it as a CLI argument, never write it to logs,
  reports, Git, issues or STATUS. Logs show only the host.
- Importer: https only, redirect targets limited to `*.strava.com` and `*.amazonaws.com`, max download 3 GB, zip-slip
  and absolute-path rejection, uncompressed size cap, extraction allowlist, never execute anything from the archive.
- `~/data/strava-export/` is chmod 700. Raw files and the zip never enter the repo (.gitignore + CI check, REQ-010).
- Site contains no coordinates (REQ-005, deploy guard REQ-009). It does contain ride names, dates, gear and times,
  which Martin accepted as public.
- Fixtures are synthetic. Real activity IDs/names never appear in tests.

## Decisions

### D-001: File-only route instead of the Strava API
Context: the API needs a paid subscription (403 inactive app). · Options: pay; hybrid; files only. ·
Decision: files only (Martin, 2026-10-23). · Consequences: no official segments/KOMs; own segments + matcher; new rides
arrive via a new export.

### D-002: Python pipeline + Vite/TypeScript static frontend
Context: FIT parsing + interactive charts. · Options: A Python + Vite/TS; B all Node; C Python + Jinja. ·
Decision: A (Martin). · Consequences: two toolchains (pip + npm); Node is needed for Playwright anyway.

### D-003: Static site on GitHub Pages, built and deployed from the VPS
Context: raw data lives only on the VPS, so GitHub Actions cannot build the site. · Options: public repo + gh-pages;
private repo + separate public site repo; VPS over Tailscale. · Decision: public repo, VPS pushes the build to
`gh-pages` (Martin). · Consequences: repo goes public before the first deploy (check history for data first);
deploys are commits on `gh-pages`, never on main.

### D-004: Segments defined in a YAML file in the data dir, no map
Context: no segment data in the export; Martin wants it simple, no map, segments by name. · Options: YAML in repo;
YAML in data dir; UI editor. · Decision: `~/data/strava-export/segments.yaml`, edited via `sdash segment add` (ride + km)
or `import-strava`. · Consequences: adding a segment needs no PR, only `sdash refresh`; the file is not versioned, so
`refresh` keeps the last 10 copies in `segments.bak/`.

### D-005: Hash routing, JSON per page
Context: GitHub Pages has no SPA rewrites. · Decision: `#/…` routes; each page fetches only its own JSON. ·
Consequences: simple, works offline from `vite preview`.
