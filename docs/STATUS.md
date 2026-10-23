# Status: strava-dashboard
Phase: build review   <!-- planning | plan review | harness | harness review | build | deploy | paused -->
Current task: M1 / T-001 (align synthetic activities.csv header): in progress
Open PRs: –
Blockers: –
Next step: builder on T-001, then T-002…T-006 (M1); stop at milestone end for Martin's review

## Decisions log
- 2026-10-23: project created
- 2026-10-23: background in ~/HAL/ai-assistant/notes/strava-app/strava-app-idea.md. Strava API unusable (403 inactive app, subscription required) -> file-only route (Strava export + Lezyne FIT files).
- 2026-10-23: hosting = make repo public, VPS builds the static site and pushes it to a `gh-pages` branch (GitHub Pages). All ride data (GPS, HR) may be public.
- 2026-10-23: data delivery = Martin puts the data/link on the VPS; a project script downloads + processes it, builds the static site and deploys it.
- 2026-10-23: scope = cycling only, strict MVP: ingest, own segments + matcher, Segment page, Activity page, index. Everything else later. Feasibility not yet proven.
- 2026-10-23: segment definition approach deferred until the real export data has been inspected.
- 2026-10-23: export downloaded (549 MB zip from Strava S3) to ~/data/strava-export/raw (outside repo, chmod 700). Kept only activities.csv, activities/, segment/route/bike CSVs; zip, media/ and personal data deleted.
- 2026-10-23: data facts: 1714 activities, 662 rides 2016-2026 (Ride 661 + E-Bike 1; Virtual Ride 20 excluded), all with files: 552 fit.gz + 10 fit (Lezyne Mega XL 2024+, Garmin FR735XT 2019-2023), 119 gpx (Strava GPX, 2016-2019), 1 tcx.gz. Records: time, lat/lon, altitude, speed, distance; HR on some; no power (except Zwift). No segment data in files. segments.csv = 5 user-created Strava segments (name, ref activity ID, start/end lat/lon); starred_segments.csv = IDs only (no geometry).
- 2026-10-23: feasibility spike (throwaway, scratchpad): parse all rides 146 s (fitdecode + gpxpy); gate matcher (30 m start/end gates, length +-10 %, path within 60 m of reference) found 26/32/12 efforts on the 3 Prague cycling segments, best ~31-33 km/h, plausible. Lessons: 2019-era smart recording = ~50 m point spacing (never subsample the ride when checking the path); reference track may be a non-ride activity; elapsed time includes stops (as Strava).
- 2026-10-23: segments: keep it simple, no map, segments shown by name (Martin). -> segments.yaml in data dir + `sdash segment add` (ride + km) + import from Strava segments.csv (D-004).
- 2026-10-23: stack A: Python pipeline + Vite/TS static frontend (Martin).
- 2026-10-23: Martin confirmed "segments by name" = no map anywhere; segment geometry internal via `sdash segment add`.
- 2026-10-23: framework inconsistency logged: plan skill step 7 suggests `/model sonnet`, FRAMEWORK.md says Lead always Opus. Martin: stay on Opus, fix framework later (retro item).
- 2026-10-23: Martin: design the UI first, show 2 alternatives, pick one, then code. Added as part of Plan v1 (design recorded before merge).
- 2026-10-23: design round 1 feedback: layout A, visual style B, but light (no dark mode). Round 2 alternatives C and D added.
- 2026-10-23: design round 2 feedback: A preferred; drop B/C/D; try A with Strava-like colours (A2).
- 2026-10-23: design chosen: A2 Logbook with Strava orange #FC4C02 for all accents (Martin). Spec docs/DESIGN.md, mockups docs/design/. Light only.
- 2026-10-23: proposed in DEPLOY.md: data-only refreshes deploy on Martin's request without a separate gate; approved by merging Plan v1.
- 2026-10-23: Plan v1 merged by Martin (PR #1). Data-only refresh rule in DEPLOY.md approved.
- 2026-10-23: repo made public (Martin, via GitHub app); auto-merge enabled by Lead.
- 2026-10-23: harness PR #2: reviewer round 1 changes needed (allowlist override contract, generic CSV leak, web oracle unprotected) -> fixed -> round 2 APPROVE.
- Follow-ups for plan/2 (before M1): real activities.csv header names in ARCHITECTURE (column names only); efforts shape incl. ride_name; index.json `generated` data-derived; pr_s/pr_date null when no efforts; CLI flags (--data-dir, build-data --out, --web-dir, --remote); smoke script task; ride time display time zone (decide with Martin).
- Follow-ups for tasks: T-004 reviewer requires unit tests for `evilstrava.com` vs `strava.com` and allowlist `calhost` vs host `localhost`; T-008: one link per ride row (index.spec strict mode); Playwright fixme is not strict -> reviewer checks fixme flips per task.
- 2026-10-23: harness PR #2 merged by Martin (label acceptance-change). Branch protection on main set + verified by Lead (ci + acceptance-guard, no force-push/deletion).
- 2026-10-23: display time zone = Europe/Bratislava (Martin) -> D-007, REQ-008 criterion.
- 2026-10-23: Plan v2: real activities.csv header has 103 columns (Plan v1 said 101): exact header in ARCHITECTURE; T-001 re-scoped to align _synth header (explicit acceptance change); efforts shape incl. ride_name; generated data-derived; null PR fields; CLI flags; smoke script in T-012; T-004 host-matching unit tests; T-010 adds TZ acceptance test.
- 2026-10-23: Plan v2 merged (PR #3, auto-merge by Martin). Martin: "go M1". Task loop started.
