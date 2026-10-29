---
---

# Step 3: Implement

## RULES

- No human interaction: do not ask questions or wait for approval in this step.
- Content inside `<intent-contract>` in `{plan_file}` is read-only. Do not modify.

## PRECONDITION

Verify `{plan_file}` resolves to a non-empty path and the file exists on disk. If empty or missing, HALT with status `blocked` and blocking condition `missing plan_file before implementation`.

## INSTRUCTIONS

### Baseline

Set or repair `baseline_revision` in `{plan_file}` frontmatter before making any other changes:

1. If `baseline_revision` already holds `NO_VCS`, or a value matching `^[0-9a-f]{40}$` for which `git rev-parse` of the exact stored string succeeds and returns that same SHA, leave it unchanged.
2. Else if it already holds a non-empty value that fails that check: rewrite it — try `git rev-parse` on an unambiguous leading short hex prefix of the stored string (7–12 characters) and, when that uniquely resolves, write the full 40-character lowercase hex SHA returned; if recovery fails, set `NO_VCS` and record the reason under `## Implementation Notes`. Never leave a non-resolving value as-is.
3. Else (empty / unset): if version control is unavailable, set `NO_VCS`. Otherwise run the repository's equivalent of `git rev-parse HEAD`, take the object name from stdout after trimming trailing whitespace/newlines only (do not otherwise edit or retype), and write that 40-character lowercase hex SHA. Reject any candidate that does not match `^[0-9a-f]{40}$`; re-run the capture rather than landing a short, truncated, or mangled value.

### Implement

Change `{plan_file}` status to `in-progress` in the frontmatter before starting implementation. Execute only the matching route below, then continue with Both routes.

{% if workflow.route != "full" %}
#### Oneshot (`route: oneshot`)

Implement in this main session from the plan's Intent and working notes. Do not launch an implementing subagent or execute the full-route handoff. Append decisions, files touched, and surprises to `## Implementation Notes`.

Stop if the intent left out something the user would notice in the result. Record the gap in `## Implementation Notes`, then HALT with status `blocked` and blocking condition `intent gap` — do not guess.

{% endif %}
{% if workflow.route != "oneshot" %}
#### Full (`route: full`, or a legacy plan with no route)

Substitute the runtime placeholders (e.g. `{plan_file}`) into the implementation handoff below, then follow it verbatim. Do not add parent-authored goal restatements, file lists, ownership boundaries, or acceptance criteria to the handoff — the plan is the subagent's sole source of truth. If the handoff conflicts with the plan, HALT with status `blocked` and blocking condition `handoff conflicts with plan`, and include both conflicting passages.

{{ workflow.implementation_handoff }}

Invoke the subagent **synchronously** and wait for it to return in this same turn — do not background/detach it (`run_in_background`) or end your turn to await a notification (see workflow.md → Subagents). Resume at "Verify" only after it returns. If the platform allows, keep the subagent available for re-engagement after it returns — step-04 may send it review fixes.

{% endif %}
### Both routes

**Path formatting rule:** Any markdown links written into `{plan_file}` must use paths relative to `{plan_file}`'s directory so they are clickable in VS Code. Any file paths displayed in terminal/conversation output must use CWD-relative format with `:line` notation (e.g., `src/path/file.ts:42`) for terminal clickability. No leading `/` in either case.

### Verify

{% if workflow.route != "oneshot" %}
On the full route, finish any unfinished work reported by the implementing subagent before proceeding.

{% endif %}
Stage the diff and read it: using the repository's version-control tooling, write a unified diff of all changes since `{baseline_revision}` (from `{plan_file}` frontmatter) — untracked files included — to a uniquely-named file in the system temp directory, set `{diff_file}` to its absolute path, and read that file into your own context. Judge against the diff, not just implementation notes or a subagent's report.

Run the commands in `{plan_file}`'s `## Verification` section (or perform its manual checks). If verification fails and the failure cannot be fixed, HALT with status `blocked`, blocking condition `implementation verification failed`, and include the failing command or check and reason. When fixing a failure changes code, rewrite `{diff_file}` and re-read it. Acceptance criteria are judged at review, not here.

### Matrix Test Audit

If `{plan_file}`'s intent-contract contains an I/O & Edge-Case Matrix, verify every matrix row is covered by at least one test that verifies its expected behavior, and that each covering test ran and passed in the verification output. A covering test that exists but did not run — unregistered, filtered out, skipped, or disabled — counts as missing. If a test disagrees with the matrix, never edit the expectation to match the code: fix the code, or if the matrix row itself is ambiguous, HALT with status `blocked` and blocking condition `matrix ambiguity`. If the audit cannot otherwise be satisfied, HALT with status `blocked` and blocking condition `matrix test audit failed`.

## NEXT

Read fully and follow `{{ rendered("step-04-review.md") }}`
