# Retrospective: strava-dashboard
Written 2026-10-30 by the Project Lead after the first production deploy. Sources: docs/LOG.md, docs/STATUS.md,
`gh pr list --state all`, `gh run list --status failure`, `git log`, `~/.claude/framework/bin/usage.py report`.

## Timeline and numbers
| Date | Phase | What |
|---|---|---|
| 2026-10-23 | plan | interview, export download, feasibility spike, 2 design rounds, Plan v1 (#1) |
| 2026-10-23 | harness | test-architect harness (#2, 2 review rounds), branch protection, Plan v2 (#3) |
| 2026-10-23..24 | M1 pipeline | T-001..T-006 (#5-#10), seeded-bug check (#4, closed), M1 PR #11 |
| 2026-10-24 | M2 site | Plan v3 (#12), T-013..T-015, T-007..T-010 (#13-#20), M2 PR #21 |
| 2026-10-25..27 | M3 fixes + refresh/deploy | Plan v4 (#22), T-016..T-018, T-011, T-012 (#23-#27), M3 PR #28 |
| 2026-10-27..29 | M4 deploy readiness | Plan v5 (#29), T-019..T-022 (#30-#33), M4 PR #34 |
| 2026-10-30 | deploy | first deploy main 0ad4e96 → gh-pages 5dceb27, record PR #35 |

- 8 calendar days (about 5 working days; 3 pauses for usage limits or session resets).
- 35 PRs: 5 plan, 1 harness, 22 task (all merged, 0 reverts), 4 milestone, 1 record, 2 throw-away (closed).
- 50 commits on main.
- **Fix rounds per task** (from STATUS):

  | Fix rounds | Tasks |
  |---|---|
  | 0 | T-001, T-004, T-013, T-022 |
  | 1 | T-002, T-003, T-005, T-006, T-007, T-008, T-010, T-011, T-012, T-014, T-015, T-017, T-018, T-019, T-021 |
  | 2 | T-009 |
  | 3 | T-016, T-020 |

  Mean 1.1. No task hit the escalation limit without merging.
- **Models**: Lead, reviewer, test-reviewer and test-architect ran on Opus 5.5. Builder ran on Sonnet 5.5.
- **Cost**: about $148 API-list equivalent in total, 1586 agent-minutes, 97 % cache hit. Per milestone: M3 about $17.8, M4 about $9.4.
- **Result**: the site is live at https://martinsuba.github.io/strava-dashboard/.
  - 662 rides, 5 segments.
  - Staging and production smoke checks passed.
  - No coordinates and no raw files are on gh-pages.

## Martin's inputs (from docs/LOG.md): by gate, could an agent have done it?
There are 41 Martin input lines in LOG.md, excluding the "(none)" and "(agent)" rows.

| Kind | Count | Agent could do it? |
|---|---:|---|
| Gate decisions (merge plan/harness/milestone PRs, "go Mx", approve deploy) | 13 | n: these are the framework's gates |
| Owner/taste decisions (hosting, scope, stack, segment approach, 3 design rounds, time zone, bad-segment policy) | 11 | n |
| Budget/session pauses and resumes | 6 | n (account limits) |
| Export link / pointing to notes | 3 | 1 y: the Lead could have searched ~/HAL for the project name itself |
| Permission workarounds (repo public, scratchpad cleanup, real-data copy) | 3 | y, with permission rules (see proposals) |
| Questions the Lead could have answered with a default | 3 | partly: M2 review (3 of 6 were "up to you"), Plan v5 (3 questions where the Lead had already recommended all three), T-016 merge OK |
| **Corrections to the Lead** | 2 | y |

The 2 corrections to the Lead:
- **Milestone PR screenshots didn't render, reported twice.** The cause was relative links. It's fixed in the next-task skill and in memory.
- **Plan skill step 7 contradicted FRAMEWORK.md** on the Lead's model. That's fixed in the skill now.

Post-deploy (2026-10-30), Martin asked twice what is on the site:
1. "What about putting all the data there?"
2. "Nothing there", about a 2026 ride page with 0 segments.

Both point to the product gap described under **Post-deploy finding**. It wasn't a bug, but the plan never showed Martin how few rides would have segments.

## What the gates caught / what slipped through
**Caught by the reviewer (Opus), in about 20 of 22 tasks:**
- Security: path traversal via CSV IDs (T-002), a YAML alias bomb and control characters (T-006), a malformed-FIT crash found by fuzzing (T-003), slow-drip download deadline (T-014), git env/worktree hardening (T-012), guard gaps (T-011).
- Correctness: lost laps when start == end (T-005), per-year buckets in UTC instead of local time (T-007), a stuck "Loading…" view on encoded URLs (T-010), untested median wiring (T-021), tests that never reached the code under test (T-020).

**Caught by the test-reviewer:**
- The seeded-bug check (#4): it correctly said CHANGES NEEDED on a weakened assertion.
- Hand-mutation checks on the T-020/T-021/T-022 acceptance edits all passed.

**Caught by CI:**
- A chart destroyed by a late dispose (T-009).
- A mutation guard masked by `| tee` (T-015).

**Caught by the Lead's real-data checks (not a framework step yet):**
- M1: 4 bugs. Thousands separators, the out-and-back reference, one bad segment failing all of them, TCX with a text prefix.
- M2: a chart bug. It was never reproduced in M3 and was probably a capture artifact. That cost T-016 3 fix rounds (about $6.4).
- None of these were visible with synthetic data.

**Slipped through to deploy:**
- **The production data dir had no `segments.yaml`.** All real-data checks used private copies with their own segments file. The Lead found the gap during deploy pre-checks and created the file with `sdash segment import-strava`. DEPLOY.md's one-time setup doesn't mention it.
- **Product coverage, the biggest miss.** Only 28 of 662 rides (4 %) have any segment effort, and none after 2021. No gate measures "does the site show Martin something useful for a typical ride?"

## Post-deploy finding (2026-10-30): segments per ride
**Facts:**
- 5 segments came from Strava's `segments.csv`. 3 are cycling segments on one Prague route; 2 were drawn on a Sitno hike and have 0 efforts.
- 28 of 662 rides have efforts, all from 2019-2021. A 2026 ride page shows "No segments matched on this ride."

**What Martin wants:**
- Strava-like behaviour: open any ride, see the segments on it, and click through to all efforts on each.
- The ride page and segment page already behave this way. The missing piece is segments where he rides now.

**Constraint:**
- The export has no public segment geometry or efforts: `starred_segments.csv` has 7 IDs only, and `local_legend_segments.csv` has 1 ID and a name.
- The Strava API is unusable (decision of 2026-10-23), and scraping strava.com breaks Strava's terms.

**Proposal (deferred by Martin, "not yet"):**
- A throwaway spike on real data in the scratchpad, with nothing in the repo. It auto-detects segments from his own rides:
  - climbs, e.g. ≥3 % for ≥500 m
  - stretches ridden on ≥5 rides
- Segments get neutral names ("Climb 1.8 km, 5 %") plus a rename CLI. Reverse geocoding is avoided: Nominatim would send coordinates to a third party, and an offline OSM extract is heavy for this 4 GB VPS.
- Report: segment count, rides with ≥1 effort, and a sample. If it looks good, a plan PR follows for a new milestone.

**Lesson for the framework:** see proposal 1.

## Process failures (agents' side)
- **Lead reported a bug from eyeballing a screenshot** (M2 chart dots). It cost a must-fix plan item and 3 fix rounds, and the bug was never reproduced. The Lead also misread a screenshot once in T-016. Rule since then: measure, don't eyeball.
- **Lead asked questions it could have defaulted.** That was 3 of 6 in the M2 review and the 3 in Plan v5, about 6 Martin-minutes.
- **Lead context grew to 752k tokens** (max ctx). The Lead was 58 % of total cost ($85.65), mostly from cache reads (214.5M) on long branches (T-009 Lead run $9.00, M2 milestone run $7.79).
- **Planning didn't measure the value metric** (rides with ≥1 effort) on the real data, although the spike had all the data needed. See Post-deploy finding.
- **Missing prerequisite in DEPLOY.md:** creating `segments.yaml` in the production data dir.
- **acceptance-guard noise:** 30 failed acceptance-guard runs on task and harness PRs. They're red until the test-review status or label arrives and need a re-run. This isn't a real failure, but it hides real ones in `gh run list --status failure`.
- **Permission check friction:**
  - The Lead couldn't make the repo public, so Martin did it.
  - It couldn't `rm -rf` scratchpad clones holding real GPS data, or copy real data for checks.
  - It couldn't run `sdash deploy` against a local bare repo in the M4 review.
- **Stuck GitHub Actions runs**, seen twice. They blocked the concurrency group; the Lead cancelled them manually.
- **Seeded-bug branch name** `chore/seeded-bug` gives the check away to the reviewer.
- **Shared checkout/scope creep:** none observed. T-011 scope was explicitly kept to PLAN text.
- **Flaky tests:** none observed. T-022 has a fixed 1 s wait (noted as non-blocking).

## Test quality (unit, acceptance, screenshots, mutation, spike/staging)
- **Python:** 468 unit tests pass (304 test functions plus parametrize). 117 pipeline acceptance tests pass, with 0 xfail left.
- **Web:** about 56 vitest cases and 24 Playwright acceptance specs. 16 screenshots per milestone.
- **Mutation (CI, matcher):**
  - M1: the workflow was broken. 488 mutants, all "not checked", but CI showed green. Found by the Lead.
  - M2: 81.7 % (91 survivors).
  - M3: 97.0 %. 15 survivors, all argued equivalent and spot-checked by the reviewer.
- **Spike:** the feasibility spike on 2026-10-23 proved parsing (146 s) and matching. It measured efforts per segment but not coverage per ride.
- **Staging (2026-10-30):** a real-data build with `refresh --no-deploy`. The smoke test passed (index, segment page, ride page), with 0 coordinate hits.
- **Production:** title, 662 rides in `index.json` and the smoke test all passed. Pages build took about 1 min.

## Cost and model fit
From `usage.py report`: 110 runs, about $148.43, 1586 min, cache hit 97 %.

| By agent | runs | $ | share | min | max ctx |
|---|---:|---:|---:|---:|---:|
| lead (Opus) | 40 | 85.65 | 58 % | 746 | 752k |
| reviewer (Opus) | 26 | 28.32 | 19 % | 287 | 174k |
| builder (Sonnet) | 23 | 17.69 | 12 % | 448 | 132k |
| test-architect (Opus) | 1 | 11.95 | 8 % | 66 | 290k |
| test-reviewer (Opus) | 20 | 4.82 | 3 % | 39 | 39k |

| By phase | runs | $ | share | min |
|---|---:|---:|---:|---:|
| task | 89 | 95.49 | 64 % | 1002 |
| harness | 3 | 16.49 | 11 % | 161 |
| milestone | 6 | 16.32 | 11 % | 373 |
| plan | 6 | 12.36 | 8 % | 33 |
| main | 5 | 7.42 | 5 % | 8 |

| Top runs | task | $ | min | max ctx |
|---|---|---:|---:|---:|
| test-architect harness | T-001 | 11.95 | 66 | 290k |
| lead on T-009 | T-009 | 9.00 | 62 | 678k |
| lead on milestone M2 | | 7.79 | 60 | 739k |
| lead on T-003 | T-003 | 7.48 | 68 | 367k |
| lead on plan/1 | | 6.87 | 22 | 209k |
| lead on milestone M1 | | 6.07 | 89 | 479k |

**Where the money went:**
- Lead cache reads on huge contexts. Lead cost per task fell from about $7-9 (M1/M2, context over 600k) to about $1.5-3.7 (M4, after the /clear between milestones).
- The builder on Sonnet was cheap: $0.77 per run on average.
- The reviewer earned its cost: it found every security issue.

**Saving ideas (estimated $-equiv per milestone):**
- **Lead /clear or handoff at every milestone start, plus a context cap (~300k) with a STATUS checkpoint and restart:** about $5-8 per milestone. M4 at 153k max ctx cost $9.4 in total; M2 at 700k+ was about 2-3x that.
- **Reviewer at lower effort for test-only or docs-only tasks** (T-019, T-022 type): about $1 per milestone. Keep full Opus for pipeline and security code.
- **Skip real-data reproduction of unconfirmed UI bugs, and measure before filing:** T-016's 3 rounds cost about $4 extra (one-off).
- **No task needed a stronger model.** The builder on Sonnet handled every task within 3 rounds.

## Proposals for the framework (ranked by Martin-minutes saved vs risk)
1. **Value check on real data in the plan spike.**
   - The spike must compute the user-visible coverage metric (here: % of rides with ≥1 segment effort, by year) and show it to Martin before Plan v1 is approved.
   - Would have surfaced the 4 % coverage and the "Strava-like segments" expectation on day 1 instead of after deploy.
   - Saves a re-plan, about 30+ Martin-min. Risk: low.
   - File: `~/.claude/skills/plan/SKILL.md` (spike step).
2. **Real-data check as a standard milestone step.** This is the 3rd time it's been proposed.
   - Lead builds privately from real data, measures, and nothing is committed.
   - Add a project hook `scripts/real_data_check` (or a DEPLOY.md "staging" command) that the milestone step runs.
   - Saves bugs found late; it caught 5 here. Risk: low.
   - Files: `~/.claude/skills/next-task/SKILL.md` (milestone section), `~/.claude/framework/templates/DEPLOY.md`.
3. **Permission rules.** **Needs Martin / settings change.** Saves 3+ interruptions per project. Risk: medium (scoped rules only).
   - (a) `gh repo edit --visibility public` for the Project Lead, which Martin asked for.
   - (b) `rm -rf` inside the session scratchpad.
   - (c) Copying real data into `~/data/*-check` (outside repos).
   - (d) Local bare-repo deploy tests under the scratchpad.
   - File: `~/.claude/settings.json` (permissions.allow), plus FRAMEWORK.md noting the rules.
4. **Deploy pre-checks include data-dir prerequisites.**
   - The deploy skill checks the project's runtime inputs (here `segments.yaml`) and DEPLOY.md lists them under one-time setup.
   - Saves a surprise at deploy. Risk: low.
   - Files: `~/.claude/skills/deploy/SKILL.md` step 2, `~/.claude/framework/templates/DEPLOY.md`. Project: add to docs/DEPLOY.md in the next plan PR.
5. **Default instead of asking.**
   - When the Lead has a recommendation and the choice is reversible, it decides, notes it in STATUS, and lists it in the milestone PR for veto.
   - Saves about 5 Martin-min per milestone review. Risk: low.
   - Files: `~/.claude/FRAMEWORK.md`, `~/.claude/skills/next-task/SKILL.md` (milestone review questions).
6. **Lead context discipline.**
   - /clear at each milestone start (already done since M3), and a STATUS checkpoint plus restart when context passes ~300k.
   - Saves about $5-8 per milestone. Risk: low.
   - File: `~/.claude/FRAMEWORK.md` (Lead section).
7. **Measure, don't eyeball.**
   - A UI bug from a screenshot needs a measured repro (element coords or test hook) before it becomes a must-fix plan item.
   - Saves about $4 and 1 Martin decision per incident. Risk: low.
   - File: `~/.claude/skills/next-task/SKILL.md` (milestone real-data check).
8. **Blind seeded-bug branch name.**
   - Use a neutral `task/T-0xx-*`-style name instead of `chore/seeded-bug`.
   - Improves trust in the test-reviewer. Risk: low.
   - File: `~/.claude/skills/next-task/SKILL.md` line 36-38.
9. **acceptance-guard re-run on status.**
   - Trigger the guard on `status` events (test-review), so it isn't red-then-rerun and `--status failure` stays meaningful.
   - Saves Lead noise. **Needs Martin's acceptance-change label** in each project.
   - Files: `~/.claude/framework/templates/` acceptance-guard workflow; project `.github/workflows/acceptance-guard.yml`.
10. **Lead searches ~/HAL notes for the project name at plan start.**
    - Saves 1 Martin input. Risk: low.
    - File: `~/.claude/skills/plan/SKILL.md` step 1.

Already fixed during the project: plan skill step 7 model note, PLAN.md ticks only in the milestone PR, absolute image links in milestone PRs.
