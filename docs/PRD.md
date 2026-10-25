# PRD: strava-dashboard
Status: approved (Plan v1, PR #1); Plan v2 + v3 + v4 amendments · Last update: 2026-10-23

## Problem & why
Martin wants to compare **all his own times on every segment over time**. Strava shows this only with a paid
subscription, and the Strava API now needs a paid subscription too (verified 2026-10-23: the old API app returns
`403 Application Status: Inactive`). Martin's ride files are his own data: Strava's account export contains the original
FIT/GPX file of every activity. A small pipeline can time every ride against segments Martin defines and publish the
results as a static website.

Background and brainstorm: `~/HAL/ai-assistant/notes/strava-app/strava-app-idea.md` (outside the repo).

## Users
Martin only, as the single rider and data owner. The site is public (GitHub Pages) and read-only; visitors just view it.

## Goals (measurable where possible)
- G1: one command turns a Strava export link (or a local zip) into an updated, deployed site, with no manual steps.
- G2: every cycling ride in the export (662 rides, 2016–2026) is parsed; unparseable files are listed, never silently dropped.
- G3: for each defined segment, the site lists every effort over all years with its rank, gap to PR and a trend chart.
- G4: for each ride, the site shows how each matched segment compares with the PR and the typical (median) time ("was this a good day?").
- G5: no raw export data (FIT/GPX files, messages, contacts, media) ever lands in Git or on the site.

## Non-goals (explicitly out of scope for the MVP)
- Strava API usage of any kind (OAuth, webhooks, official segments, KOM/leaderboards).
- Maps, GPS tracks or route display (Martin, 2026-10-23: "we don't need a map"). Segments are shown by name.
- Running, hiking, virtual rides (Zwift) and other sports. MVP covers `Ride` and `E-Bike Ride` only.
- Defining segments by clicking in the UI. Segments are defined in a file, with a CLI helper.
- Friends, multi-user, logins, comments.
- Effort compare overlays, fitness/freshness, power curve, weather adjustment, heatmaps, matched routes, LLM summary.
  These are candidates for later milestones via a new plan PR.
- Automatic scheduled refresh. Martin triggers a refresh when he has new data.
- A backend/server at runtime. The site is static.

## Requirements

### REQ-001: Import a Strava export
The `refresh`/`import` command accepts either an https download link or a path to a local export zip, and stores only
ride data in the data directory (outside the repo).
Acceptance criteria:
- Given a local export zip containing `activities.csv`, `activities/`, `media/`, `messages.json`-style personal files,
  When `sdash import <zip>` runs, Then the data dir contains `activities.csv`, `activities/` and `segments.csv`, and contains no `media/` and no other personal files.
- Given a zip with an entry whose path escapes the target (`../x`, absolute path), When importing, Then the import fails with a clear error and writes nothing outside the data dir.
- Given a zip whose total uncompressed size exceeds the limit (default 3 GB), When importing, Then it fails before extracting.
- Given a URL that is not https, When importing, Then it fails without any network request.
- Given a successful import from a downloaded zip, Then the downloaded zip is deleted afterwards.
- Given an existing import, When a newer export is imported, Then the old ride files are replaced by the new ones (the newer export is a superset).
Priority: must

### REQ-002: Parse rides
Read `activities.csv` and each cycling activity's file into a normalised track (time, lat, lon, cumulative distance).
Acceptance criteria:
- Given activities of types Ride, E-Bike Ride, Run, Virtual Ride, When parsing, Then only Ride and E-Bike Ride are kept.
- Given ride files in `.fit`, `.fit.gz`, `.gpx`, `.gpx.gz` (and `.tcx.gz`, priority could), When parsing, Then each yields a track with timestamps and positions; records without a position are skipped.
- Given a file that cannot be parsed, When parsing, Then the run continues, and the activity ID plus reason appear in the run report.
- Given `activities.csv` rows (of any activity type) whose numbers use a thousands separator (e.g. Distance `2,496`), When reading the CSV, Then those rows are read correctly and no row is silently dropped. (Plan v3, real-data finding)
- Given a TCX file with whitespace, a BOM or other text before the XML declaration (as in Strava's own TCX export), When parsing, Then it yields a track. (Plan v3)
- Given a ride already parsed and unchanged, When parsing again, Then it is read from the cache and not re-parsed.
- Given the `Activity Date` format `Oct 20, 2026, 3:45:46 AM` (UTC) and duplicated column names in `activities.csv`, When reading the CSV, Then date, name, type, gear, distance and filename are read correctly (first occurrence of a duplicated column wins).
Priority: must (tcx.gz: could)

### REQ-003: Segment definitions
Segments are defined in a YAML file in the data directory: name, start lat/lon, end lat/lon, reference activity ID.
Acceptance criteria:
- Given a valid segments file, When the pipeline runs, Then each segment gets a stable slug derived from its name.
- Given a segment with a missing field, an out-of-range coordinate or a duplicate name, When the pipeline runs, Then it reports an error naming the segment and the problem and exits non-zero.
- Given one invalid or unusable segment (bad fields, duplicate name, missing or unusable reference track) next to valid segments, When `match`, `build-data` or `refresh` runs, Then the bad segment is reported (name + problem) and skipped, all valid segments are still matched and built (and deployed by `refresh`), and the command exits with code 2 ("finished with warnings"). An unreadable `segments.yaml` (not valid YAML) still fails the whole run. (Plan v3, Martin 2026-10-24)
- Given a ride ID and a start km and end km, When `sdash segment add --name N --activity ID --from-km A --to-km B` runs, Then a segment with the coordinates at those distances on that ride is appended to the segments file.
- Given Strava's `segments.csv` from the export, When `sdash segment import-strava` runs, Then its segments are added to the segments file (skipping names that already exist).
Priority: must

### REQ-004: Segment matching
Find every effort of every segment in every ride.
Acceptance criteria:
- Given a ride that passes within 30 m of the start, later within 30 m of the end, with a ridden distance within ±10 % of the reference length and every reference point within 60 m of the ride path, When matching, Then one effort is recorded with elapsed time = time at end − time at start (stops included, as on Strava).
- Given a ride that passes the start and end but takes a different road (a reference point is farther than 60 m), Then no effort is recorded.
- Given a ride that rides the segment in the opposite direction, Then no effort is recorded.
- Given a ride that rides the segment twice (e.g. two laps), Then two efforts are recorded.
- Given a sparse track (one point per ~50 m, "smart recording"), Then the effort is still found.
- Given a segment whose start and end are the same place (out-and-back), Then the effort is found and is not a zero-length match.
- Given an out-and-back segment whose reference activity jitters in and out of the start/end gate before riding the segment, When building the reference, Then too-short gate pairs are skipped and the real out-and-back run is used. (Plan v3, real-data finding)
- Given a segment whose reference activity is not a ride (e.g. a hike), Then the reference track is still used.
Priority: must

### REQ-005: Site data
The pipeline writes derived JSON only, which the static site reads.
Acceptance criteria:
- Given parsed rides and matched efforts, When building site data, Then it contains a ride list, a segment list and per-segment and per-ride effort data, and contains no GPS coordinates or raw track data.
- Given the same inputs, When building twice, Then the output is byte-identical (deterministic).
Priority: must

### REQ-006: Index page
Acceptance criteria:
- Given site data, When opening the site, Then a segment list shows each segment's name, effort count, PR time and PR date, and a ride list shows rides newest first with date, name, distance and number of matched segments.
- Given a segment or ride in the lists, When clicking it, Then its page opens.
- Given no segments defined, Then the segment list shows an empty-state message explaining how to add one.
Priority: must

### REQ-007: Segment page
Acceptance criteria:
- Given a segment with efforts, When opening its page, Then a table lists all efforts with date, ride name, elapsed time, average speed, rank and gap to PR, sortable by date and by time (default: by time).
- Given the efforts, Then the top three are marked PR, 2nd and 3rd.
- Given the efforts, Then a chart shows elapsed time against date, with the PR highlighted.
- Given the efforts, Then a summary shows effort count per year and best time per year.
- Given a segment with no efforts, Then the page says so instead of showing an empty table or chart.
- Given efforts spread over several years, When the chart is drawn, Then every dot is drawn at its effort's actual date on the time axis. (Plan v4, M2 real-data finding)
- Given a few efforts far slower than the rest (e.g. long stops included in elapsed time), When the chart is drawn, Then the time axis is capped at about twice the median elapsed time, slower efforts are shown as markers at the edge of the chart, and the chart states how many efforts are beyond the cap. (Plan v4)
Priority: must

### REQ-008: Activity page
Acceptance criteria:
- Given a ride, When opening its page, Then it shows date, name, distance, moving/elapsed time and gear from `activities.csv`.
- Given a ride with matched segments, Then each matched effort shows elapsed time, PR time, median time (of all efforts of that segment), gap to PR, rank among all efforts, a position bar from the PR (left) to the slowest effort (right), and is marked when it is the PR (or the PR at the time it was ridden).
- Given a ride with no matched segments, Then the page says so.
- Given a ride that started at 15:05 UTC on a summer day, When any viewer opens its page (whatever their browser time zone), Then its start time shows as 17:05, because all dates and times are shown in Europe/Bratislava time (D-007).
Priority: must

### REQ-009: One-command refresh and deploy
Acceptance criteria:
- Given an export link or zip, When `sdash refresh <link|zip>` runs, Then it imports, parses, matches, builds site data, builds the static site and deploys it, printing a short report (rides parsed, failures, efforts per segment).
- Given `sdash refresh` without an argument, Then it rebuilds from the existing data (e.g. after adding a segment).
- Given `--no-deploy`, Then it stops after building the site locally.
- Given any step fails, Then nothing is deployed. Segment-level warnings (REQ-003, exit code 2) are not failures: the valid segments are built and deployed and the warnings are printed in the report.
- Given the built site, Before deploying, Then a guard verifies the output has no `.fit/.gpx/.tcx/.csv` files and no coordinate fields; it aborts otherwise.
Priority: must

### REQ-010: Raw data never in Git
Acceptance criteria:
- Given the repo, Then `.gitignore` excludes data dirs, `*.fit`, `*.fit.gz`, `*.gpx`, `*.gpx.gz`, `*.tcx.gz`, `*.zip` outside `tests/fixtures/`.
- Given a PR adding such a file outside `tests/fixtures/`, Then CI fails.
- Given test fixtures, Then they are synthetic (generated tracks at made-up places), never real rides.
Priority: must

## Constraints (budget, privacy, data, platforms)
- Desktop-first (Martin, 2026-10-25): the site is used ~99 % on desktop. Mobile only has to stay usable (no page-level horizontal scroll); no further mobile optimisation.
- Cost: free. GitHub Pages needs a **public repo** on the free plan (Martin decided: make it public).
- Privacy: Martin accepts that all ride data may be public. The MVP publishes no GPS data at all (no maps).
  The export also contains personal data (messages, contacts, logins, media): deleted right after extraction, never committed.
- Data lives on agent-vps in `~/data/strava-export/` (chmod 700), outside the repo.
- Export: ~550 MB zip today, ~95 % of it `media/`. Strava's link expires after a few days.
- New rides reach the pipeline only through a new Strava export (Lezyne → Strava sync stays as is).
- Full parse of 662 rides takes ~2.5 min (spike), so parsed rides are cached.

## Open questions
- Which segments Martin wants first beyond the 3 Prague ones from `segments.csv`. He will give ride + km ranges after the MVP is live.
