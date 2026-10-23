# strava-dashboard
Follows Martin's framework: ~/.claude/FRAMEWORK.md (skills: plan, harness, next-task, deploy).
State: docs/STATUS.md (read it first). Plan: docs/PRD.md, docs/ARCHITECTURE.md, docs/PLAN.md. Tests: docs/TESTS.md.

## Stack
Python 3.12 pipeline (`sdash` CLI: fitdecode, gpxpy, PyYAML; ruff, mypy, pytest) + static frontend in `web/`
(Vite + TypeScript, no framework, Chart.js; eslint, prettier, vitest, Playwright). Deployed as a static site to
GitHub Pages (`gh-pages` branch) from agent-vps. See docs/ARCHITECTURE.md. UI spec: docs/DESIGN.md.

## Data (never in Git)
Real Strava export data lives in `~/data/strava-export/` (raw/, cache/, segments.yaml), chmod 700, outside the repo.
Tests use synthetic fixtures only (tests/fixtures/). Never commit or publish raw files, coordinates or export links.

## Commands
- Install:
- Run:
- Lint / typecheck:
- Unit tests:
- Acceptance tests:

## Conventions
(filled in during harness)
