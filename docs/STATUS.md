# Status: strava-dashboard
Phase: planning   <!-- planning | plan review | harness | harness review | build | deploy | paused -->
Current task: plan v1 (branch plan/1): waiting for Martin's Strava export link, then inspect data, then write PRD/PLAN
Open PRs: –
Blockers: Strava export not yet on the VPS (Martin to provide download link)
Next step: download export to ~/data/strava-export/ (outside repo), keep only ride data, inspect formats; decide segment definition approach with Martin

## Decisions log
- 2026-10-23: project created
- 2026-10-23: background in ~/HAL/ai-assistant/notes/strava-app/strava-app-idea.md. Strava API unusable (403 inactive app, subscription required) -> file-only route (Strava export + Lezyne FIT files).
- 2026-10-23: hosting = make repo public, VPS builds the static site and pushes it to a `gh-pages` branch (GitHub Pages). All ride data (GPS, HR) may be public.
- 2026-10-23: data delivery = Martin puts the data/link on the VPS; a project script downloads + processes it, builds the static site and deploys it.
- 2026-10-23: scope = cycling only, strict MVP: ingest, own segments + matcher, Segment page, Activity page, index. Everything else later. Feasibility not yet proven.
- 2026-10-23: segment definition approach deferred until the real export data has been inspected.
- Open: standing approval for automatic data-only redeploys (to propose in DEPLOY.md).
