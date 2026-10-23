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
