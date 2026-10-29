# Deploy: strava-dashboard

## Target
Static site on **GitHub Pages**, served from the `gh-pages` branch of `martinsuba/strava-dashboard`:
`https://martinsuba.github.io/strava-dashboard/`. The site is built on agent-vps, because the raw data lives only there.

## One-time setup (deploy phase, before the first deploy)
1. Check that the repo history has no raw data or secrets: `git log --all --stat` must show no `.fit/.gpx/.tcx/.zip/.csv`
   outside `tests/fixtures/`, and no export link.
2. ~~Make the repo public~~: done by Martin on 2026-10-23.
3. The first deploy (`sdash refresh`) creates the `gh-pages` branch. Then enable Pages:
   `gh api -X POST repos/martinsuba/strava-dashboard/pages -f 'source[branch]=gh-pages' -f 'source[path]=/'`.
   If the API call is refused (403, the token may lack the Pages permission), Martin sets it once in GitHub:
   Settings → Pages → Source "Deploy from a branch", branch `gh-pages`, folder `/ (root)`.

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
Exit codes: 0 = built and deployed; 2 = built and deployed **with warnings** (one or more segments skipped, listed in
the report as `warning: … (segment skipped)`; fix `segments.yaml` and refresh again); 1 = a step failed, nothing deployed.
`refresh` imports, parses, matches, builds the site, runs the output guard, and pushes `web/dist` as a new commit on
`gh-pages` (never a force-push, never main). The export link is passed only on the command line, never logged or saved.

`sdash deploy [--web-dir W] [--remote R]` does only the last step on an already built `web/dist`
(`npm --prefix web run build` first). `refresh --no-deploy` stops before it. **Use `sdash refresh` for real deploys**:
after `npm run test:acceptance` or `npm run screenshots`, `web/public/data` and `web/dist` hold the synthetic fixture
site; `sdash deploy` refuses (exit 1, nothing pushed) a dist without a matching `data/build-info.json` (D-008),
which only `sdash build-data` writes. Details:
- `--remote` is a git remote name, URL or path; default `origin`. Tests use a local bare repo.
- The guard runs first; on any finding nothing is committed or pushed.
- The commit is built in a temporary git worktree (removed afterwards, also on failure) on top of the remote's
  `gh-pages` (a root commit if it does not exist yet). It contains only the contents of `web/dist` plus an empty
  `.nojekyll`. The push is a plain fast-forward of `gh-pages`; a rejected push is an error (exit 1), never retried with force.
- Git calls ignore `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE` and similar variables from the environment, and only the
  deploy's own worktree is removed (it never runs `git worktree prune` or touches other worktrees). If git has no commit identity configured, the
  commit is authored as `sdash deploy <sdash@localhost>`.
- If `web/dist` is identical to what `gh-pages` has, nothing is committed and the command prints `nothing to deploy`.

## Smoke checks after deploy
- `curl -sf https://martinsuba.github.io/strava-dashboard/ | grep -q '<title>'` (Pages may take ~1 min).
- `curl -sf https://martinsuba.github.io/strava-dashboard/data/index.json` and check that the number of `rides` = the
  report's `parsed N rides` + the failed count (every cycling ride in `activities.csv` gets an index row, also one whose
  file failed to parse).
- Open one segment page and one ride page: `npm --prefix web run smoke -- --base https://martinsuba.github.io/strava-dashboard/`
  (Playwright; finds a segment and a ride link on the index; fails on page errors, console errors, failed requests or
  HTTP >= 400; from T-019 on it also waits for each page's loaded content). Also works against the staging preview:
  `--base http://localhost:4173/strava-dashboard/`.
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

**First deploy**: `gh-pages` then has only a root commit, which `git revert` cannot undo into a previous build. Rollback
= take the site down: Settings → Pages → Source "None" (or `gh api -X DELETE repos/martinsuba/strava-dashboard/pages`),
then fix and deploy again (re-enable Pages as in the one-time setup). The `gh-pages` history is never rewritten or
deleted; every deploy adds one commit on top.

## Secrets needed (names only; values set by Martin in GitHub/target)
None in GitHub. The deploy pushes over SSH with the VPS's existing deploy key/SSH key for `origin`
(`git@github.com:martinsuba/strava-dashboard.git`), not with the `gh` login (`gh` is only used for the Pages API call).
The export link is a short-lived credential: argument only, never stored (note: a command-line argument is visible in
`ps` while `refresh` runs; reading it from stdin is a later nice-to-have).

## History (date · commit · target · result)
