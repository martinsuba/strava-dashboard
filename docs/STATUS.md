# Status: strava-dashboard
Phase: paused review   <!-- planning | plan review | harness | harness review | build | deploy | paused -->
Current task: M1 / T-003 PR #7 in review (paused 2026-10-23: Claude usage limit near). Done: T-001 (PR #5), T-002 (PR #6)
Open PRs: #7 T-003 (branch task/T-003-formats-cache)
Blockers: usage limit (pause requested by Martin)
Next step: on resume, see "Resume here" below

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
- 2026-10-23: seeded-bug check: PR #4 (chore/seeded-bug) weakened the REQ-004 stop tolerance 5 s -> 75 s; test-reviewer said CHANGES NEEDED (correct). Closed unmerged, branch kept.
- 2026-10-23: T-001 merged (PR #5): reviewer + test-reviewer approve, 0 fix rounds.
- Follow-up (needs a task allowed to edit workflows): CI "Install Playwright browser" step sometimes takes ~11 min (apt deps); fix with the Playwright container image or caching.
- Note: task progress ticks live in STATUS.md during a milestone; PLAN.md ticks go into the milestone PR (merge condition d forbids PLAN.md in task PRs).
- 2026-10-23: T-002 merged (PR #6): 1 fix round (reviewer: build-data deleted foreign JSON recursively; path traversal via CSV Activity ID/Filename and ref_activity -> fixed + unit tests). Test-reviewer approved 16 marker removals.
- For T-005: when a (start,end) pair fails direction/path/length, move to the next start pass instead of consuming the end pass; add the A->B, B->A, A->B ride as a unit test (reviewer probe3).
- For T-003: test_req002_changed_ride_is_parsed_again must keep passing once the cache exists.
- Milestone PR todo: TESTS.md status column (16 tests now passing after T-002), PLAN.md ticks.
- 2026-10-23: paused on Martin's note "approaching claude limit". Task loop stopped mid-T-003.

## Resume here (written 2026-10-23 at pause)
State of T-003 / PR #7 (https://github.com/martinsuba/strava-dashboard/pull/7):
- Builder done: code commit 9140e0a (FIT/TCX/.gz parsing, 200 MB bounded decompression, TCX DOCTYPE/ENTITY refusal, size+mtime cache). Local checks reported green: pytest unit 82 passed, acceptance 52 passed / 45 xfailed.
- CI on 9140e0a: ci pass, screenshots pass, acceptance-guard fail (expected until test-review).
- Reviewer was running on 9140e0a when paused (focus: XML entity expansion for TCX and GPX/gpxpy, gz cap, cache). Check for its PR comment ("Review verdict: … (SHA 9140e0a)").
- This STATUS commit moves the PR head past 9140e0a (docs-only delta). Merge condition c needs the reviewer's APPROVE for the CURRENT head: if 9140e0a was approved, ask the reviewer to confirm the new head (diff vs 9140e0a = docs/STATUS.md only), then run the test-reviewer (test_parse.py marker changes: FORMATS list now plain names), rerun acceptance-guard, merge with --match-head-commit.
- Fix rounds used on T-003: 0 of 3.
Then continue M1: T-004 (import, security-relevant; add unit tests evilstrava.com vs strava.com and calhost vs localhost), T-005 (full matcher; include reviewer note: when a (start,end) pair fails direction/path/length, move to the next start pass; add A->B, B->A, A->B ride unit test), T-006 (segments). Then milestone M1 PR (TESTS.md status column + PLAN.md ticks, screenshots, mutation report) and stop for Martin.
To resume: Martin says "continue" (or "resume M1") in the strava-dashboard Lead session; Lead reads this section, `git status`, `gh pr list`.
