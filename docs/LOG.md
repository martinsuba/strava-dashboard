# Martin inputs log
One line per input Martin had to give. Used for retrospectives (what can be automated?).

date | gate/phase | what Martin did | could an agent do it? (y/n + why)
--- | --- | --- | ---
2026-10-23 | plan | pointed Lead to his notes (~/HAL/.../strava-app-idea.md) | y: Lead could have searched for notes on the project name itself
2026-10-23 | plan | decided hosting (public repo + gh-pages), data delivery via VPS script, cycling-only MVP | n: owner decisions
2026-10-23 | plan | asked to provide Strava export download link | n: link only reachable from Martin's email
2026-10-23 | plan | pasted Strava export email link | n: link only in Martin's email (Lead downloaded it fine from the VPS)
2026-10-23 | plan | chose segment approach (simple, no map) and stack A | n: owner decisions
2026-10-23 | plan | confirmed segment interpretation; decided Lead stays on Opus despite plan skill step 7 suggesting `/model sonnet` (conflicts with FRAMEWORK.md "Lead always Opus") -> framework fix later | y: inconsistency in framework docs; fix plan skill step 7 so no question is needed
2026-10-23 | plan | asked for a UI design step with 2 alternatives before coding | n: owner preference (framework could add a design step to the plan skill for web UI projects)
2026-10-23 | plan | design feedback round 1 (A layout + B style, light only) | n: taste decision
2026-10-23 | plan | design feedback round 2 (keep A, try Strava-like colours) | n: taste decision
2026-10-23 | plan | picked design A2, all accents Strava orange | n: taste decision
2026-10-23 | plan gate | merged Plan v1 PR #1 | n: gate decision
2026-10-23 | harness | (agent) enabled Actions, created label acceptance-change; auto-merge + branch protection refused while repo private on free plan | y: done by agent
2026-10-23 | harness | decided to make repo public now (needed for auto-merge/branch protection on free plan) | n: owner decision
2026-10-23 | harness | made repo public himself in the GitHub app: Lead's `gh repo edit --visibility public` was blocked by Claude Code auto-mode classifier [Create Public Surface] | y: Martin wants the Lead able to do this next time -> add a permission rule (framework/settings fix, retro item)
2026-10-23 | harness | (agent) enabled allow_auto_merge after repo went public | y: done by agent
2026-10-23 | harness | (none needed) reviewer round 1 issues fixed by test-architect, round 2 approve | y: done by agents
2026-10-23 | harness gate | added acceptance-change label and merged harness PR #2 | n: gate decision (label is the human approval of protected tests)
2026-10-23 | harness | (agent) set + verified branch protection on main | y: done by agent
2026-10-23 | plan v2 | decided display time zone Europe/Bratislava | n: owner preference
2026-10-23 | M1 gate | merged Plan v2 (auto-merge) and said "go M1" | n: gate decision
2026-10-23 | M1 | (none) seeded-bug check passed: test-reviewer rejected weakened assertion on PR #4 | y: done by agents. Framework note: required branch name `chore/seeded-bug` reveals the test to the reviewer
2026-10-23 | M1 | (none) framework inconsistency: next-task step 8 says tick PLAN.md in the next task branch, merge condition d forbids PLAN.md in task PRs -> ticks in STATUS, PLAN in milestone PR | y: fix next-task skill
2026-10-23 | M1 | (none) test-reviewer report claimed Martin's label was still needed although its own test-review status satisfies acceptance-guard | y: clarify in test-reviewer agent prompt
2026-10-23 | M1 | (none) T-002 merged after 1 fix round (security issues found by reviewer) | y: done by agents
2026-10-23 | M1 | paused the task loop: Claude usage limit approaching | n: account/budget decision
2026-10-24 | M1 | resumed task loop after usage-limit pause ("continue") | n: budget decision
2026-10-24 | M1 | (none) T-003 merged after 1 fix round | y: done by agents
2026-10-24 | M1 | (none) T-004 merged, 0 fix rounds | y: done by agents
2026-10-24 | M1 | (none) T-005 merged after 1 fix round | y: done by agents
2026-10-24 | M1 | (none) T-006 merged; M1 complete; Lead ran real-data check and found 4 bugs synthetic tests missed | y: done by Lead. Framework idea: make a real-data smoke check a standard milestone step
2026-10-24 | M1 | (none) scratchpad cleanup (`rm -rf` of old clones + spike pickles with real GPS) blocked by permission check | n: Martin must allow or delete
