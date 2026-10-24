# Status: strava-dashboard
Phase: build   <!-- planning | plan review | harness | harness review | build | deploy | paused -->
Current task: M2 / T-013 (real-data fixes from the M1 check): in progress
Open PRs: –
Blockers: –
Next step: builder on T-013, then T-014, T-015, T-007…T-010; stop at M2 end for Martin's review

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
- 2026-10-24: resumed (Martin: "continue").
- 2026-10-24: T-006 merged (PR #10): 1 fix round (control chars in names broke segments.yaml; YAML alias bomb via error repr -> fixed). M1 complete.
- 2026-10-24: M1 real-data check by Lead (private dir ~/data/m1-check, raw symlinked, nothing committed): parse 661/662 rides (1 TCX fails), match 7 s; one-way Prague segments 26 + 26 efforts (prototype 26 + 32: prototype double-counted 7 out-and-back rides at the turnaround; new matcher correct and finds 1 more). Found 4 real-data bugs (below).
- 2026-10-24: T-005 merged (PR #9): 1 fix round (reviewer found lost laps when start == end and wrong reference length when ref passes start twice -> fixed; matcher 2x faster).
- 2026-10-24: T-004 merged (PR #8): 0 fix rounds; reviewer ran 89 hostile zip/URL cases, all handled.
- 2026-10-24: T-003 merged (PR #7): 1 fix round (reviewer fuzzing found malformed-FIT crash -> fixed; 5000-mutation re-fuzz clean). Test-reviewer approved marker removals.

## M1 real-data findings (-> Plan v3: T-013, T-014, T-015)
1. activities.csv numbers with thousands separators (`2,496`, Distance of Swim/Rowing rows) make read_activities fail for non-cycling rows; reference_only_activities swallows the error -> non-ride reference tracks (e.g. the Sitno hike) are silently never parsed.
2. Out-and-back segment (start == end, "Trojský most - Přívoz Klecánky otočka"): GPS jitter at the gate pairs passes 7 m apart -> degenerate-reference error. Reference pairing must skip too-short pairs and try the next end pass.
3. One invalid segment makes `match`/`build-data` fail for ALL segments (no site data at all). Should report the bad segment and still process the others (needs a PRD/TESTS decision: exit code).
4. TCX with text before the XML declaration (Strava's own TCX export) fails to parse (1 ride).
5. Mutation workflow is broken: 488 mutants all "not checked" (deprecated mutmut config keys); green but empty. Needs a workflow task (Martin's label).
Plus small hardening leftovers (T-003 N1-N5, T-004 reviewer items, T-006: >4300-digit int in YAML -> traceback). CI Playwright-install slowness needs a workflow task (Martin's label).

## Follow-ups (open)
- T-005 reviewer non-blocking: `is_reference = act in extra` -> set of IDs (pipeline.py); test_pipeline imports private `_reference`. Matcher bench (synthetic worst case 660 rides × 4000 pts × 5 segments): 43 s, 444 MB.
- T-003 reviewer non-blocking (candidate fix/ task or fold into T-005/T-007): N1 include exception type name in FIT failure reasons (tracks.py:174); N2 `_num_list` must reject JSON Infinity (tracks.py:226/239, match crashes on hand-corrupted cache); N3 drop dead `p.latitude is None` check, test lat-less trkpt -> reported failure; N4 DTD test `match="DTD"` + UTF-32 case; N5 drop vacuous `except ValueError: return` in fuzz test (test_tracks.py:290); N6 `_refuse_dtd` decodes up to 5x (ok for TCX).
- T-004 reviewer non-blocking: name the entry on file/dir clash (importer.py:238); cap number of zip entries; overall download deadline (slow drip); chmod existing data dir 0700; clean stale .raw-old-*/.raw-staging-*/.download-* after a kill; opt-in redacted debug traceback (cli.py:142); note in ARCHITECTURE that proxies are ignored. Real link hosts (email.strava.com -> s3.amazonaws.com, seen 2026-10-23) match the allowlist.
- CI: "Install Playwright browser" sometimes ~11 min (needs a task allowed to edit workflows).
- Milestone PR: TESTS.md status column (tests un-marked in T-002/T-003), PLAN.md ticks.
- 2026-10-24: Martin: a bad segment must not stop the build: report it and still build the rest -> Plan v3 (REQ-003/009 criteria, exit code 2, refresh still deploys).
- 2026-10-24: M1 PR #11 screenshots did not render (relative image links in a PR body). Fixed with absolute raw.githubusercontent.com links pinned to the commit, verified via body_html. Root cause in ~/.claude/skills/next-task/SKILL.md fixed (absolute links + verify step). Martin reported it as the second time.
- 2026-10-24: M1 milestone PR #11 merged by Martin.
- 2026-10-24: Plan v3 merged (PR #12). Martin: "go M2".
