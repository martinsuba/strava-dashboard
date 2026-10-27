# Deploy: strava-dashboard

## Target
Static site on **GitHub Pages**, served from the `gh-pages` branch of `martinsuba/strava-dashboard`:
`https://martinsuba.github.io/strava-dashboard/`. The site is built on agent-vps, because the raw data lives only there.

## One-time setup (deploy phase, before the first deploy)
1. Check that the repo history has no raw data or secrets: `git log --all --stat` must show no `.fit/.gpx/.tcx/.zip/.csv`
   outside `tests/fixtures/`, and no export link.
2. With Martin's go: make the repo public: `gh repo edit martinsuba/strava-dashboard --visibility public --accept-visibility-change-consequences`.
3. First `sdash deploy` creates the `gh-pages` branch. Then enable Pages:
   `gh api -X POST repos/martinsuba/strava-dashboard/pages -f 'source[branch]=gh-pages' -f 'source[path]=/'`.

## Environments (staging? production)
- **Staging = local preview on the VPS with real data**: `sdash refresh <link|zip> --no-deploy`, then
  `npm --prefix web run preview -- --host 0.0.0.0 --port 4173`. Reachable only over Tailscale at `http://agent-vps:4173/strava-dashboard/`.
  Smoke checks run here first.
- **Production** = GitHub Pages.

## Approval rule
- **Code changes** (anything in the repo that changes what gets built): first deploy after a milestone needs Martin's approval (framework gate).
- **Data-only refresh** (new export, new or changed segment in `segments.yaml`, same code on main): Martin's request
  ("refresh with this link", "add segment X") counts as approval; the Lead runs `sdash refresh` without asking again.
  Merging the Plan v1 PR approves this standing rule.

## How to deploy (exact steps / commands / workflow)
On agent-vps, in the repo, on an up-to-date `main`:
```
git switch main && git pull
source .venv/bin/activate && pip install -e . && npm --prefix web ci
sdash refresh '<export link>'      # or a local zip path, or no argument to rebuild from existing data
```
`refresh` imports, parses, matches, builds the site, runs the output guard, and pushes `web/dist` as a new commit on
`gh-pages` (never a force-push, never main). The export link is passed only on the command line, never logged or saved.

`sdash deploy [--web-dir W] [--remote R]` does only the last step on an already built `web/dist`
(`npm --prefix web run build` first). `refresh --no-deploy` stops before it. Details:
- `--remote` is a git remote name, URL or path; default `origin`. Tests use a local bare repo.
- The guard runs first; on any finding nothing is committed or pushed.
- The commit is built in a temporary git worktree (removed afterwards, also on failure) on top of the remote's
  `gh-pages` (a root commit if it does not exist yet). It contains only the contents of `web/dist` plus an empty
  `.nojekyll`. The push is a plain fast-forward of `gh-pages`; a rejected push is an error (exit 1), never retried with force.
- If `web/dist` is identical to what `gh-pages` has, nothing is committed and the command prints `nothing to deploy`.

## Smoke checks after deploy
- `curl -sf https://martinsuba.github.io/strava-dashboard/ | grep -q '<title>'` (Pages may take ~1 min).
- `curl -sf https://martinsuba.github.io/strava-dashboard/data/index.json` and check the ride count = the report's count.
- Open one segment page and one ride page: `npm --prefix web run smoke -- --base https://martinsuba.github.io/strava-dashboard/`
  (Playwright; finds a segment and a ride link on the index; fails on page errors, console errors, failed requests or
  HTTP >= 400). Also works against the staging preview: `--base http://localhost:4173/strava-dashboard/`.
- The deployed files contain no coordinates: the guard runs before the push; re-check with `grep -rE '"(lat|lon|start|end)"' web/dist/data` → no matches.

## Rollback
`gh-pages` has one commit per deploy. Rollback = a new commit that undoes the bad one, pushed normally (never force):
```
git fetch origin gh-pages
git worktree add /tmp/gh-pages-rollback origin/gh-pages --detach
cd /tmp/gh-pages-rollback && git revert --no-edit HEAD && git push origin HEAD:refs/heads/gh-pages
cd - && git worktree remove /tmp/gh-pages-rollback
```
Pages serves the previous build within ~1 min. Alternatively fix the data/code and run `sdash refresh` again.

## Secrets needed (names only; values set by Martin in GitHub/target)
None in GitHub. The deploy pushes with the VPS's existing `gh` login. The export link is a short-lived credential:
argument only, never stored.

## History (date · commit · target · result)
