# Status: strava-dashboard
Phase: plan review   <!-- planning | plan review | harness | harness review | build | deploy | paused -->
Current task: Plan v1 PR open (branch plan/1)
Open PRs: #1 Plan v1
Blockers: –
Next step: Martin reviews and merges the Plan v1 PR; then harness skill

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
- 2026-10-23: proposed in DEPLOY.md: data-only refreshes deploy on Martin's request without a separate gate; approved by merging Plan v1.
