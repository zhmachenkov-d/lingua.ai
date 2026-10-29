# Finalize: Retrospective Document

Phase 5. Finalize the retrospective document.

## The retrospective document

This document is the run's working artifact: it is created as a skeleton once the epic is fixed and filled as each phase completes, so Phase 5 finalizes rather than writes it from scratch. It lives at `<epic folder>/epic-<slug>-retrospective.md`, as readable markdown — a fixed name, so a resumed run finds it.

Open the document with YAML frontmatter a machine can read without parsing the prose — an epic gate or orchestrator keys off `verdict` / `closure` / `action_items`:

```
---
epic: epic-<slug>
date: {date}
verdict: accepted | accepted-with-open-items | rejected
closure: recommended | refused
criteria: declared | profiled
headless: true | false
action_items:
  - id: R2026-1
    kind: remediation | spec-reconciliation | process
    disposition: fix-now | defer | accept-as-is
    title: Short title
    owner: role or name
    summary: One paragraph with source refs
---
```

`epic` is the folder's name, as `tickets.py` spells the epic. Keep `verdict` in sync with the Acceptance verdict section below. Set `closure: recommended` when `verdict` is `accepted` or `accepted-with-open-items`, and `closure: refused` when `verdict` is `rejected`. Every routed Action items section entry must appear in `action_items` with a stable `id` (unique within the epic). This frontmatter is the machine-readable contract; nothing else in the tree records the verdict, so a gate or orchestrator that acts on it **must** read this file.

Sections:

- **Epic summary** — which epic, its tickets with their statuses, the tickets still at `built`, any tickets still unfinished (`pending_tickets`) that the user accepted retro-ing over, each plan's range, the evidence inventory (what was available, what was missing). Unfinished tickets force the machine acceptance verdict to **rejected** (see `{{ rendered("references/acceptance-verdict.md") }}`).
- **Findings** — grouped by aggregate view and by lens, each with its source reference and disposition (fix now / defer / accept). This is the record; do not summarize away the provenance.
- **Behavior verification** — what was exercised end to end and what was observed, or an explicit note that runtime behavior was not exercised.
- **Previous-retro follow-through** — if a prior retro exists, whether its action items landed, with evidence (`{{ rendered("references/acceptance-verdict.md") }}` specifies what to record).
- **Action items** — the routed fix-now items and process lessons, each with an owner. Note which are proposed remediation or spec reconciliations awaiting human application.
- **Decision records** — each decision proposed as a record, and whether it was approved and written (`{{ rendered("references/acceptance-verdict.md") }}` specifies what to record).
- **Acceptance verdict** — accepted / accepted-with-open-items / rejected, whether the criteria were declared or profiled, and the evidence behind the call.
- **Open questions** — what a human answer would materially change, and anything the analyses could not resolve.
- **Assumptions** — in headless runs, every choice made without the user: how the epic reference resolved to its folder, any non-empty `pending_tickets`, a machine **rejected** verdict forced by unfinished tickets or rendered with no human decision, each proposed item and decision record. Omit in interactive runs — an interactive run records the same facts where the user confirmed them, in Epic summary.

Do not state time estimates anywhere in the document.

## Finish

Report the document's path, the verdict, `closure`, action-item counts by disposition (`fix-now` / `defer` / `accept-as-is`), and the path of each decision record written. Nothing else was written by this skill: no epic `status` change, no backlog tickets, and no tree file edited beyond this document (and approved ADRs). Say that `bmad_factory` or Sofia Closure validate will close the epic and/or open backlog tickets from `closure` and `action_items` when appropriate.

## On Complete

If anything appears below, follow it as the final terminal instruction before exiting; otherwise exit normally.

{{ workflow.on_complete }}
