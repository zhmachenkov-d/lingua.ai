"""Tickets-mode pick: pure :func:`decide_pick` over ``next`` / ``status`` views.

Behavior-port of upstream ``bmad_loop.tickets_source`` (tickets-only). No mux,
no coding-agent CLIs, no work-source engine wrapper — the orchestrator CLI calls
:func:`decide_pick` directly and dispatches through Cursor SDK.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Protocol

from .plan_status import PLAN_BLOCKED, PLAN_STATUS_ORDER
from .ticketmodel import EpicRow, NextView, StatusView, TicketRow

# --------------------------------------------------------------------------- phases


class Phase(StrEnum):
    """Unit phases the pick cares about (touched vs ESCALATED wedge)."""

    PENDING = "pending"
    DEV_RUNNING = "dev-running"
    DEV_VERIFY = "dev-verify"
    REVIEW_RUNNING = "review-running"
    REVIEW_VERIFY = "review-verify"
    COMMITTING = "committing"
    DONE = "done"
    DEFERRED = "deferred"
    ESCALATED = "escalated"
    AWAITING_OPERATOR = "awaiting-operator"


# --------------------------------------------------------------------------- halt / pause


HALT_REFINE: Final = "refine"
HALT_HITL: Final = "hitl"
HALT_PLAN_CHECKPOINT: Final = "plan-checkpoint"
HALT_AWAITING_CLOSURE: Final = "awaiting-closure"
HALT_EPIC_CLOSURE: Final = "epic-closure"
HALT_EPIC_REJECTED: Final = "epic-rejected"
HALT_BLOCKED_PLAN: Final = "blocked-plan"
HALT_FOREIGN_ACTIVE: Final = "foreign-active"
HALT_STALLED: Final = "stalled"
HALT_TREE_FAULT: Final = "tree-fault"
HALT_PIN_MISMATCH: Final = "pin-mismatch"
HALT_DIRTY_INITIATIVE: Final = "dirty-initiative"
HALT_IGNORED_PLAN: Final = "ignored-plan"

PAUSE_EPIC_BOUNDARY: Final = "epic-boundary"
PAUSE_ESCALATION: Final = "escalation"
PAUSE_PLAN_CHECKPOINT: Final = "plan-checkpoint"
PAUSE_TICKET_HITL: Final = "ticket-hitl"
PAUSE_TICKET_REFINE: Final = "ticket-refine"
PAUSE_TICKET_TREE: Final = "ticket-tree"

HALT_STAGES: Final[Mapping[str, str]] = {
    HALT_REFINE: PAUSE_TICKET_REFINE,
    HALT_HITL: PAUSE_TICKET_HITL,
    HALT_PLAN_CHECKPOINT: PAUSE_PLAN_CHECKPOINT,
    HALT_AWAITING_CLOSURE: PAUSE_EPIC_BOUNDARY,
    HALT_EPIC_CLOSURE: PAUSE_EPIC_BOUNDARY,
    HALT_EPIC_REJECTED: PAUSE_EPIC_BOUNDARY,
    HALT_BLOCKED_PLAN: PAUSE_ESCALATION,
    HALT_FOREIGN_ACTIVE: PAUSE_TICKET_TREE,
    HALT_STALLED: PAUSE_TICKET_TREE,
    HALT_TREE_FAULT: PAUSE_TICKET_TREE,
    HALT_PIN_MISMATCH: PAUSE_TICKET_TREE,
    HALT_DIRTY_INITIATIVE: PAUSE_TICKET_TREE,
    HALT_IGNORED_PLAN: PAUSE_TICKET_TREE,
}

SKIP_EMPTY: Final = "empty"
SKIP_PARKED: Final = "parked"

NOTE_SKIPPED: Final = "skipped"
NOTE_FOREIGN_ACTIVE: Final = "foreign-active"

CLOSURE_REJECTED: Final = "rejected"
EPIC_CLOSED: Final = frozenset({"done", "dropped"})
_TICKET_FINISHED: Final = frozenset({"done", "dropped"})

BOUNDARY_RETRO: Final = "retro"
BOUNDARY_REJECTED: Final = "rejected"
BOUNDARY_ACK: Final = "ack"
BOUNDARY_PAUSE: Final = "pause"

THOROUGH_ALWAYS: Final = "always"
THOROUGH_HIGH_RISK: Final = "high-risk"
THOROUGH_NEVER: Final = "never"
RISK_HIGH: Final = "high"

MARK_DONE_AUTO: Final = "auto"
MARK_DONE_NEVER: Final = "never"

SOURCE_TICKETS: Final = "tickets"


# --------------------------------------------------------------------------- decisions


@dataclass(frozen=True)
class PickNote:
    kind: str
    ref: str
    why: str
    phase: str = ""


@dataclass(frozen=True)
class Dispatch:
    row: TicketRow
    notes: tuple[PickNote, ...] = ()

    @property
    def ref(self) -> str:
        assert self.row.ref is not None
        return self.row.ref


@dataclass(frozen=True)
class Skip:
    reason: str
    held: tuple[str, ...] = ()
    waiting: tuple[str, ...] = ()
    notes: tuple[PickNote, ...] = ()


@dataclass(frozen=True)
class Halt:
    cause: str
    key: str
    row: TicketRow | None
    detail: str
    notes: tuple[PickNote, ...] = ()

    @property
    def stage(self) -> str:
        return HALT_STAGES[self.cause]


PickDecision = Dispatch | Skip | Halt


@dataclass(frozen=True)
class EpicBoundary:
    action: str
    slug: str
    verdict: str = ""


@dataclass(frozen=True)
class PickScope:
    epic: str = ""
    ref: str = ""

    def admits(self, row: TicketRow) -> bool:
        if self.epic and row.epic != self.epic:
            return False
        return not self.ref or row_label(row) == self.ref

    def admits_epic(self, slug: str) -> bool:
        return not self.ref and (not self.epic or slug == self.epic)


EVERYTHING: Final = PickScope()


# --------------------------------------------------------------------------- helpers


def row_label(row: TicketRow) -> str:
    return row.ref or row.file or f"{row.epic}/{row.id}"


def needs_refine(row: TicketRow) -> bool:
    return row.refine and not row.refined


def plan_planned(status: str) -> bool:
    return status in PLAN_STATUS_ORDER and PLAN_STATUS_ORDER.index(
        status
    ) >= PLAN_STATUS_ORDER.index("ready-for-dev")


def is_plan_halt_leg(row: TicketRow) -> bool:
    return row.plan_checkpoint and not row.refined and not plan_planned(row.status)


def wants_thorough(thorough_review: str, risk: str) -> bool:
    if thorough_review == THOROUGH_ALWAYS:
        return True
    return thorough_review == THOROUGH_HIGH_RISK and risk.strip().lower() == RISK_HIGH


def dispatch_invocation(skill: str, ref: str, *, thorough: bool, plan_halt: bool) -> str:
    line = f"/{skill} ticket {ref}"
    if thorough:
        line += " thorough"
    if plan_halt:
        line += " Halt after planning."
    return line


def plan_blocked(row: TicketRow) -> bool:
    return row.status == PLAN_BLOCKED or bool(row.blocked_at)


def build_order(status_view: StatusView) -> dict[str, int]:
    return {row_label(row): i for i, row in enumerate(status_view.tickets)}


def epic_finished(status_view: StatusView, slug: str) -> bool:
    rows = [t for t in status_view.tickets if t.epic == slug]
    return bool(rows) and all(t.status == "built" or t.state in _TICKET_FINISHED for t in rows)


def epic_boundary(
    status_view: StatusView,
    closures: Mapping[str, str],
    acked: Sequence[str] | frozenset[str],
    committed: frozenset[str],
    *,
    resumed: Sequence[str] | frozenset[str],
) -> list[EpicBoundary]:
    out: list[EpicBoundary] = []
    for epic in status_view.epics:
        if epic.status in EPIC_CLOSED or epic.folder is None:
            continue
        slug = epic.slug
        verdict = closures.get(slug)
        if verdict is None:
            if slug in committed and epic_finished(status_view, slug):
                out.append(EpicBoundary(BOUNDARY_RETRO, slug))
        elif verdict == CLOSURE_REJECTED:
            if epic_finished(status_view, slug):
                out.append(EpicBoundary(BOUNDARY_REJECTED, slug, verdict))
        elif slug in acked:
            continue
        elif slug in resumed:
            out.append(EpicBoundary(BOUNDARY_ACK, slug, verdict))
        else:
            out.append(EpicBoundary(BOUNDARY_PAUSE, slug, verdict))
    return out


def _ordered(rows: Sequence[TicketRow], rank: Mapping[str, int]) -> list[TicketRow]:
    last = len(rank)
    keyed = sorted(enumerate(rows), key=lambda p: (rank.get(row_label(p[1]), last), p[0]))
    return [row for _, row in keyed]


def _awaiting_closure(status_view: StatusView) -> list[str]:
    out: list[str] = []
    for epic in status_view.epics:
        if epic.status in EPIC_CLOSED:
            continue
        states = [t.state for t in status_view.tickets if t.epic == epic.slug]
        if states and all(s in _TICKET_FINISHED for s in states):
            out.append(epic.slug)
    return out


def _unbroken_epics(status_view: StatusView) -> list[EpicRow]:
    with_tickets = {t.epic for t in status_view.tickets}
    return [
        e for e in status_view.epics if e.status not in EPIC_CLOSED and e.slug not in with_tickets
    ]


def _behind_held(
    rows: Sequence[TicketRow], every: Sequence[TicketRow], held: Sequence[str]
) -> set[str]:
    by_id = {(r.epic, r.id): row_label(r) for r in every if r.id is not None}
    epic_of = {row_label(r): r.epic for r in every}
    behind: set[str] = set(held)
    grew = True
    while grew:
        grew = False
        epics = {epic_of[key] for key in behind if key in epic_of}
        for row in rows:
            label = row_label(row)
            if label in behind or not row.waiting_on:
                continue
            if all(
                by_id.get((row.epic, wait), wait) in behind or wait in epics
                for wait in row.waiting_on
            ):
                behind.add(label)
                grew = True
    return behind


def _rejected_gate(
    row: TicketRow, status_view: StatusView, epic_closures: Mapping[str, str]
) -> str | None:
    for epic in status_view.epics:
        if epic.slug == row.epic:
            return None
        if epic_closures.get(epic.slug) == CLOSURE_REJECTED and epic.status not in EPIC_CLOSED:
            return epic.slug
    return None


# --------------------------------------------------------------------------- decide_pick


def decide_pick(
    next_view: NextView,
    status_view: StatusView,
    task_phases: Mapping[str, Phase],
    epic_closures: Mapping[str, str],
    approvals: Sequence[str] | frozenset[str],
    scope: PickScope = EVERYTHING,
    *,
    acked: Sequence[str] | frozenset[str] = (),
) -> PickDecision:
    touched = {key: phase for key, phase in task_phases.items() if phase != Phase.ESCALATED}
    rank = build_order(status_view)
    notes: list[PickNote] = []

    def scoped(*groups: Sequence[TicketRow]) -> list[TicketRow]:
        return _ordered([row for group in groups for row in group if scope.admits(row)], rank)

    foreign = [row for row in scoped(next_view.in_progress) if row_label(row) not in touched]
    notes.extend(PickNote(NOTE_FOREIGN_ACTIVE, row_label(row), row.status) for row in foreign)

    candidates = scoped(next_view.ready_to_refine, next_view.ready_to_start)
    for row in candidates:
        if row.ref is None:
            notes.append(PickNote(NOTE_SKIPPED, row_label(row), "no-ref"))
            continue
        phase = touched.get(row.ref)
        if phase is not None:
            notes.append(PickNote(NOTE_SKIPPED, row.ref, "touched", str(phase)))
            continue
        held = tuple(notes)
        gate = _rejected_gate(row, status_view, epic_closures)
        if gate is not None:
            return Halt(
                HALT_EPIC_REJECTED,
                gate,
                row,
                f"{gate}'s retrospective verdict is rejected; close {gate} before "
                f"{row.ref} can start",
                held,
            )
        if needs_refine(row):
            return Halt(HALT_REFINE, row.ref, row, f"{row.ref} needs refining", held)
        if row.hitl:
            return Halt(HALT_HITL, row.ref, row, f"{row.ref} is a hitl ticket", held)
        if row.refined and row.plan_checkpoint and row.ref not in approvals:
            return Halt(
                HALT_PLAN_CHECKPOINT,
                row.ref,
                row,
                f"{row.ref} has a plan checkpoint: approve its story file",
                held,
            )
        return Dispatch(row, held)

    held_notes = tuple(notes)
    blocked = scoped(next_view.blocked)
    for row in blocked:
        if plan_blocked(row) and row_label(row) not in touched:
            reason = row.blocked_reason or "no reason recorded"
            return Halt(
                HALT_BLOCKED_PLAN,
                row_label(row),
                row,
                f"{row_label(row)}'s plan is blocked: {reason}",
                held_notes,
            )
    for row in blocked:
        if not plan_blocked(row) and not row.waiting_on and row.unknown:
            return Halt(
                HALT_REFINE,
                row_label(row),
                row,
                f"{row_label(row)} has an open unknown: {row.unknown}",
                held_notes,
            )
    awaiting = [slug for slug in _awaiting_closure(status_view) if scope.admits_epic(slug)]
    for row in blocked:
        for wait in row.waiting_on:
            if wait in awaiting:
                return Halt(
                    HALT_AWAITING_CLOSURE,
                    wait,
                    row,
                    f"every ticket of {wait} is done; close {wait} so {row_label(row)} can start",
                    held_notes,
                )
    if foreign:
        named = ", ".join(f"{row_label(r)} ({r.status})" for r in foreign)
        return Halt(
            HALT_FOREIGN_ACTIVE,
            row_label(foreign[0]),
            foreign[0],
            f"only tickets this run did not start stand in the way: {named}",
            held_notes,
        )
    if blocked:
        waiting_rows = [r for r in blocked if row_label(r) not in touched]
        waiting = tuple(row_label(r) for r in waiting_rows)
        own_held = [key for key, phase in touched.items() if phase != Phase.DONE] or [
            row_label(r) for r in blocked if not waiting_rows
        ]
        if own_held:
            every = (
                *status_view.tickets,
                *next_view.ready_to_refine,
                *next_view.ready_to_start,
                *next_view.in_progress,
                *blocked,
            )
            behind = _behind_held(waiting_rows, every, own_held)
            stalled = [r for r in waiting_rows if row_label(r) not in behind]
            if not stalled:
                last = len(rank)
                held = tuple(sorted(own_held, key=lambda k: (rank.get(k, last), k)))
                return Skip(SKIP_PARKED, held, waiting, held_notes)
            waiting_rows = stalled
            waiting = tuple(row_label(r) for r in stalled)
        return Halt(
            HALT_STALLED,
            waiting[0],
            waiting_rows[0],
            f"{len(waiting)} ticket(s) wait on nothing this run can start: {', '.join(waiting)}",
            held_notes,
        )
    awaiting = [slug for slug in awaiting if slug not in acked]
    if awaiting:
        return Halt(
            HALT_AWAITING_CLOSURE,
            awaiting[0],
            None,
            f"every ticket of {awaiting[0]} is done; close {awaiting[0]}",
            held_notes,
        )
    unbroken = [e for e in _unbroken_epics(status_view) if scope.admits_epic(e.slug)]
    if unbroken:
        first = unbroken[0]
        why = (
            "is declared in the initiative but has no folder yet: create it and break it down"
            if first.folder is None
            else "is open but has no tickets: break it down or close it"
        )
        return Halt(HALT_STALLED, first.slug, None, f"{first.slug} {why}", held_notes)
    return Skip(SKIP_EMPTY, notes=held_notes)


# --------------------------------------------------------------------------- resume helpers (local RunState)


class _PauseState(Protocol):
    pause_reason: str | None
    pause_ticket: str | None
    ticket_story_approvals: list[str]
    ticket_epic_closures: dict[str, str]
    ticket_epic_closure_resumed: list[str]
    task_phases: dict[str, str]
    source: str


def approve_paused_story_file(state: _PauseState) -> str | None:
    """Record story-file approval for a pick-time plan-checkpoint pause."""
    ref = state.pause_ticket
    if (
        getattr(state, "source", SOURCE_TICKETS) != SOURCE_TICKETS
        or state.pause_reason != PAUSE_PLAN_CHECKPOINT
        or not ref
        or ref in state.task_phases
        or ref in state.ticket_story_approvals
    ):
        return None
    state.ticket_story_approvals.append(ref)
    return ref


def resume_epic_closure(state: _PauseState) -> str | None:
    """Record that resume answers a non-rejected epic-closure pause."""
    slug = state.pause_ticket
    if (
        getattr(state, "source", SOURCE_TICKETS) != SOURCE_TICKETS
        or state.pause_reason != PAUSE_EPIC_BOUNDARY
        or not slug
        or state.ticket_epic_closures.get(slug, CLOSURE_REJECTED) == CLOSURE_REJECTED
        or slug in state.ticket_epic_closure_resumed
    ):
        return None
    state.ticket_epic_closure_resumed.append(slug)
    return slug
