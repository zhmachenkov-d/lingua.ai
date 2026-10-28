"""Adapted upstream decide_pick table tests for bmad_orchestrate.tickets_source."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from bmad_orchestrate import tickets_source as ts
from bmad_orchestrate.run_state import RunState
from bmad_orchestrate.ticketmodel import EpicRow, NextView, StatusView, TicketRow
from bmad_orchestrate.tickets_source import (
    PAUSE_EPIC_BOUNDARY,
    PAUSE_ESCALATION,
    PAUSE_PLAN_CHECKPOINT,
    PAUSE_TICKET_HITL,
    PAUSE_TICKET_REFINE,
    PAUSE_TICKET_TREE,
    Phase,
)

CART, CHECKOUT = "epic-cart", "epic-checkout"

_FAKE_STATE_OF = {
    "": "planned",
    "draft": "backlog",
    "ready-for-dev": "backlog",
    "in-progress": "in-progress",
    "blocked": "in-progress",
    "in-review": "review",
    "built": "review",
    "done": "done",
    "dropped": "dropped",
    "awaiting-operator": "in-progress",
}


def ticket_row(
    ref: str, *, epic: str = CART, status: str = "", **fields: object
) -> TicketRow:
    _, _, n = ref.rpartition(".")
    base: dict[str, object] = {
        "ref": ref,
        "epic": epic,
        "id": n or ref,
        "file": None,
        "type": "story",
        "tracker_id": "",
        "title": f"Ticket {ref}",
        "status": status,
        "tracker_status": "",
        "state": _FAKE_STATE_OF[status],
        "assignee": "",
        "hitl": False,
        "risk": "",
        "refine": False,
        "refined": False,
        "blocked_at": "",
        "blocked_reason": "",
        "after": (),
        "gated_by": (),
        "waiting_on": (),
        "unknown": "",
        "plan_checkpoint": False,
        "done_checkpoint": False,
        "drift": False,
        "blocks": (),
    }
    base.update(fields)
    return TicketRow(**base)  # type: ignore[arg-type]


def fake_next_view(
    *,
    store: str = "repo",
    folder: str = "initiative-demo",
    ready_to_refine: tuple[TicketRow, ...] = (),
    ready_to_start: tuple[TicketRow, ...] = (),
    in_progress: tuple[TicketRow, ...] = (),
    blocked: tuple[TicketRow, ...] = (),
) -> NextView:
    return NextView(
        store=store,
        folder=folder,
        ready_to_refine=ready_to_refine,
        ready_to_start=ready_to_start,
        in_progress=in_progress,
        blocked=blocked,
        problems=(),
        unpinned_after=(),
        undeclared_after=(),
        order_conflict=(),
    )


def fake_status_view(
    tickets: tuple[TicketRow, ...],
    *,
    store: str = "repo",
    folder: str = "initiative-demo",
    epics: tuple[EpicRow, ...] = (),
) -> StatusView:
    counts: dict[str, int] = {"total": len(tickets)}
    for t in tickets:
        counts[t.state] = counts.get(t.state, 0) + 1
    return StatusView(
        store=store,
        folder=folder,
        tickets=tickets,
        counts=counts,
        epics=epics,
        next_id=None,
        longest_remaining_chain=(),
        problems=(),
    )


def _epic(slug: str, eid: str, status: str = "in-progress", **kw) -> EpicRow:
    return EpicRow(
        slug=slug,
        id=eid,
        status=status,
        after=(),
        gated_by=kw.get("gated_by", ()),
        blocks=(),
        next_id=3,
        folder=slug,
        refined=True,
    )


EPICS = (_epic(CART, "1"), _epic(CHECKOUT, "2", gated_by=(CART,)))
UNSLICED = EpicRow(
    slug="epic-payment",
    id="3",
    status="",
    after=(),
    gated_by=(),
    blocks=(),
    next_id=None,
    folder=None,
    refined=False,
)


def _views(
    *,
    refine: tuple[TicketRow, ...] = (),
    start: tuple[TicketRow, ...] = (),
    in_progress: tuple[TicketRow, ...] = (),
    blocked: tuple[TicketRow, ...] = (),
    others: tuple[TicketRow, ...] = (),
    order: tuple[TicketRow, ...] | None = None,
    epics: tuple[EpicRow, ...] = EPICS,
) -> tuple[NextView, StatusView]:
    every = (*refine, *start, *in_progress, *blocked, *others)
    rows = (
        order if order is not None else tuple(sorted(every, key=lambda r: r.ref or ""))
    )
    return (
        fake_next_view(
            ready_to_refine=refine,
            ready_to_start=start,
            in_progress=in_progress,
            blocked=blocked,
        ),
        fake_status_view(rows, epics=epics),
    )


def _done(ref: str, epic: str = CART) -> TicketRow:
    return ticket_row(ref, epic=epic, status="done")


def _waits(ref: str, *on: str, epic: str = CART, **kw) -> TicketRow:
    return ticket_row(ref, epic=epic, waiting_on=on, **kw)


CASES = [
    pytest.param(
        _views(start=(ticket_row("1.1"), ticket_row("1.2"))),
        {},
        {},
        (),
        ("dispatch", "1.1"),
        id="first-ready-dispatches",
    ),
    pytest.param(
        _views(
            start=(ticket_row("1.2"), ticket_row("1.1")),
            order=(ticket_row("1.1"), ticket_row("1.2")),
        ),
        {},
        {},
        (),
        ("dispatch", "1.1"),
        id="build-order-is-status-order-not-next-order",
    ),
    pytest.param(
        _views(start=(ticket_row("1.1", status="ready-for-dev"), ticket_row("1.2"))),
        {"1.1": Phase.DEFERRED},
        {},
        (),
        ("dispatch", "1.2"),
        id="touched-this-run-is-skipped-not-redispatched",
    ),
    pytest.param(
        _views(start=(ticket_row("1.1"),)),
        {"1.1": Phase.ESCALATED},
        {},
        (),
        ("dispatch", "1.1"),
        id="pick-time-wedge-rereads-the-tree",
    ),
    pytest.param(
        _views(start=(ticket_row("1.1", hitl=True), ticket_row("1.2"))),
        {},
        {},
        (),
        ("halt", ts.HALT_HITL, "1.1", PAUSE_TICKET_HITL),
        id="hitl",
    ),
    pytest.param(
        _views(refine=(ticket_row("1.1", type="bug", refine=True),)),
        {},
        {},
        (),
        ("halt", ts.HALT_REFINE, "1.1", PAUSE_TICKET_REFINE),
        id="refine",
    ),
    pytest.param(
        _views(start=(ticket_row("1.1", refine=True, refined=True),)),
        {},
        {},
        (),
        ("dispatch", "1.1"),
        id="refined-bug-dispatches",
    ),
    pytest.param(
        _views(start=(ticket_row("1.1", refined=True, plan_checkpoint=True),)),
        {},
        {},
        (),
        ("halt", ts.HALT_PLAN_CHECKPOINT, "1.1", PAUSE_PLAN_CHECKPOINT),
        id="refined-plan-checkpoint-unapproved",
    ),
    pytest.param(
        _views(start=(ticket_row("1.1", refined=True, plan_checkpoint=True),)),
        {},
        {},
        ("1.1",),
        ("dispatch", "1.1"),
        id="refined-plan-checkpoint-approved",
    ),
    pytest.param(
        _views(start=(ticket_row("1.1", plan_checkpoint=True),)),
        {},
        {},
        (),
        ("dispatch", "1.1"),
        id="unrefined-plan-checkpoint-dispatches-its-halt-leg",
    ),
    pytest.param(
        _views(in_progress=(ticket_row("1.1", status="in-progress"),)),
        {},
        {},
        (),
        ("halt", ts.HALT_FOREIGN_ACTIVE, "1.1", PAUSE_TICKET_TREE),
        id="foreign-in-progress-blocks",
    ),
    pytest.param(
        _views(
            in_progress=(ticket_row("1.1", status="built"),),
            blocked=(_waits("1.2", "1"),),
        ),
        {},
        {},
        (),
        ("halt", ts.HALT_FOREIGN_ACTIVE, "1.1", PAUSE_TICKET_TREE),
        id="foreign-built-blocks",
    ),
    pytest.param(
        _views(
            in_progress=(ticket_row("1.1", status="built"),), start=(ticket_row("1.2"),)
        ),
        {},
        {},
        (),
        ("dispatch", "1.2"),
        id="foreign-built-is-passed-over-never-dispatched",
    ),
    pytest.param(
        _views(
            in_progress=(ticket_row("1.1", status="built"),), epics=(_epic(CART, "1"),)
        ),
        {"1.1": Phase.DONE},
        {},
        (),
        ("skip", ts.SKIP_EMPTY, (), ()),
        id="own-built-finishes",
    ),
    pytest.param(
        _views(
            others=(_done("1.1"),), epics=(_epic(CART, "1", status="done"), EPICS[1])
        ),
        {},
        {},
        (),
        ("halt", ts.HALT_STALLED, CHECKOUT, PAUSE_TICKET_TREE),
        id="open-epic-without-tickets-halts",
    ),
    pytest.param(
        _views(
            blocked=(
                ticket_row(
                    "1.1", status="blocked", blocked_reason="awaiting operator: x"
                ),
                _waits("1.2", "1"),
            )
        ),
        {"1.1": Phase.AWAITING_OPERATOR},
        {},
        (),
        ("skip", ts.SKIP_PARKED, ("1.1",), ("1.2",)),
        id="blocked-behind-own-parked",
    ),
    pytest.param(
        _views(
            start=(ticket_row("1.1", status="ready-for-dev"),),
            blocked=(_waits("1.2", "1"),),
        ),
        {"1.1": Phase.DEFERRED},
        {},
        (),
        ("skip", ts.SKIP_PARKED, ("1.1",), ("1.2",)),
        id="blocked-behind-own-deferred",
    ),
    pytest.param(
        _views(
            start=(ticket_row("1.1", status="ready-for-dev"),),
            blocked=(
                _waits("1.2", "1"),
                _waits("1.3", "2"),
                _waits("2.1", CART, epic=CHECKOUT),
            ),
            epics=(_epic(CART, "1"), _epic(CHECKOUT, "2")),
        ),
        {"1.1": Phase.DEFERRED},
        {},
        (),
        ("skip", ts.SKIP_PARKED, ("1.1",), ("1.2", "1.3", "2.1")),
        id="blocked-transitively-behind-own-deferred",
    ),
    pytest.param(
        _views(
            start=(ticket_row("1.1", status="ready-for-dev"),),
            blocked=(_waits("1.2", "1"), _waits("1.3", "9")),
        ),
        {"1.1": Phase.DEFERRED},
        {},
        (),
        ("halt", ts.HALT_STALLED, "1.3", PAUSE_TICKET_TREE),
        id="unrelated-wait-stalls-despite-own-deferred",
    ),
    pytest.param(
        _views(
            start=(ticket_row("1.1", status="ready-for-dev"),),
            blocked=(_waits("1.2", "1", "9"),),
        ),
        {"1.1": Phase.DEFERRED},
        {},
        (),
        ("halt", ts.HALT_STALLED, "1.2", PAUSE_TICKET_TREE),
        id="partly-unexplained-wait-stalls",
    ),
    pytest.param(
        _views(
            blocked=(ticket_row("1.1", status="blocked", blocked_reason="tests red"),)
        ),
        {},
        {},
        (),
        ("halt", ts.HALT_BLOCKED_PLAN, "1.1", PAUSE_ESCALATION),
        id="foreign-blocked-plan-escalates",
    ),
    pytest.param(
        _views(
            blocked=(ticket_row("1.1", status="blocked"),),
            start=(ticket_row("2.1", epic=CHECKOUT),),
            epics=(_epic(CART, "1"), _epic(CHECKOUT, "2")),
        ),
        {},
        {},
        (),
        ("dispatch", "2.1"),
        id="blocked-plan-does-not-hold-independent-work",
    ),
    pytest.param(
        _views(blocked=(ticket_row("1.1", unknown="which payment provider?"),)),
        {},
        {},
        (),
        ("halt", ts.HALT_REFINE, "1.1", PAUSE_TICKET_REFINE),
        id="open-unknown-needs-refining",
    ),
    pytest.param(
        _views(
            blocked=(_waits("2.1", CART, epic=CHECKOUT, gated_by=(CART,)),),
            others=(_done("1.1"), _done("1.2")),
        ),
        {},
        {},
        (),
        ("halt", ts.HALT_AWAITING_CLOSURE, CART, PAUSE_EPIC_BOUNDARY),
        id="gated-by-awaiting-closure",
    ),
    pytest.param(
        _views(others=(_done("1.1"), _done("1.2"))),
        {},
        {},
        (),
        ("halt", ts.HALT_AWAITING_CLOSURE, CART, PAUSE_EPIC_BOUNDARY),
        id="empty-with-open-epic-halts",
    ),
    pytest.param(
        _views(
            start=(ticket_row("2.1", epic=CHECKOUT),),
            others=(_done("1.1"),),
            epics=(_epic(CART, "1"), _epic(CHECKOUT, "2")),
        ),
        {},
        {CART: ts.CLOSURE_REJECTED},
        (),
        ("halt", ts.HALT_EPIC_REJECTED, CART, PAUSE_EPIC_BOUNDARY),
        id="rejected-epic-holds-the-next-epic",
    ),
    pytest.param(
        _views(start=(ticket_row("1.3"),), others=(_done("1.1"),)),
        {},
        {CART: ts.CLOSURE_REJECTED},
        (),
        ("dispatch", "1.3"),
        id="rejected-epic-runs-its-own-fixups",
    ),
    pytest.param(
        _views(
            start=(ticket_row("2.1", epic=CHECKOUT),),
            epics=(_epic(CART, "1", status="done"), _epic(CHECKOUT, "2")),
        ),
        {},
        {CART: ts.CLOSURE_REJECTED},
        (),
        ("dispatch", "2.1"),
        id="closed-rejected-epic-holds-nothing",
    ),
    pytest.param(
        _views(blocked=(_waits("1.2", "9"),)),
        {},
        {},
        (),
        ("halt", ts.HALT_STALLED, "1.2", PAUSE_TICKET_TREE),
        id="unexplained-wait-stalls",
    ),
    pytest.param(
        _views(
            start=(
                replace(ticket_row("1.1", file="story-orphan.md"), ref=None),
                ticket_row("1.2"),
            ),
            order=(ticket_row("1.2"),),
        ),
        {},
        {},
        (),
        ("dispatch", "1.2"),
        id="row-without-ref-is-skipped",
    ),
    pytest.param(
        _views(others=(_done("1.1"),), epics=(_epic(CART, "1", status="done"),)),
        {},
        {},
        (),
        ("skip", ts.SKIP_EMPTY, (), ()),
        id="empty-finishes",
    ),
]


SCOPE_CASES = [
    pytest.param(
        _views(start=(ticket_row("1.1"), ticket_row("2.1", epic=CHECKOUT))),
        {},
        {},
        (),
        ("dispatch", "2.1"),
        ts.PickScope(epic=CHECKOUT),
        id="epic-filter-passes-earlier-epics",
    ),
    pytest.param(
        _views(
            in_progress=(ticket_row("1.2", status="built"),),
            others=(_done("2.1", CHECKOUT),),
            epics=(_epic(CART, "1"), _epic(CHECKOUT, "2", status="done")),
        ),
        {},
        {},
        (),
        ("skip", ts.SKIP_EMPTY, (), ()),
        ts.PickScope(epic=CHECKOUT),
        id="epic-filter-ignores-foreign-rows-outside-it",
    ),
    pytest.param(
        _views(others=(_done("1.1"), _done("2.1", CHECKOUT))),
        {},
        {},
        (),
        ("halt", ts.HALT_AWAITING_CLOSURE, CHECKOUT, PAUSE_EPIC_BOUNDARY),
        ts.PickScope(epic=CHECKOUT),
        id="epic-filter-scopes-awaiting-closure",
    ),
    pytest.param(
        _views(
            start=(ticket_row("2.1", epic=CHECKOUT),),
            others=(_done("1.1"),),
            epics=(_epic(CART, "1"), _epic(CHECKOUT, "2")),
        ),
        {},
        {CART: ts.CLOSURE_REJECTED},
        (),
        ("halt", ts.HALT_EPIC_REJECTED, CART, PAUSE_EPIC_BOUNDARY),
        ts.PickScope(epic=CHECKOUT),
        id="epic-filter-still-held-by-a-rejected-epic",
    ),
    pytest.param(
        _views(start=(ticket_row("1.1"), ticket_row("1.2"))),
        {},
        {},
        (),
        ("dispatch", "1.2"),
        ts.PickScope(ref="1.2"),
        id="ref-filter-dispatches-only-its-ticket",
    ),
    pytest.param(
        _views(others=(_done("1.1"),), epics=(_epic(CART, "1"),)),
        {"1.1": Phase.DONE},
        {},
        (),
        ("skip", ts.SKIP_EMPTY, (), ()),
        ts.PickScope(ref="1.1"),
        id="ref-filter-finishes-without-epic-halts",
    ),
]


@pytest.mark.parametrize(
    ("views", "phases", "closures", "approvals", "expected", "scope"),
    [pytest.param(*case.values, ts.EVERYTHING, id=case.id) for case in CASES]
    + SCOPE_CASES,
)
def test_decide_pick_table(views, phases, closures, approvals, expected, scope):
    next_view, status_view = views
    decision = ts.decide_pick(
        next_view, status_view, phases, closures, approvals, scope
    )

    if expected[0] == "dispatch":
        assert isinstance(decision, ts.Dispatch), decision
        assert decision.ref == expected[1]
    elif expected[0] == "skip":
        assert isinstance(decision, ts.Skip), decision
        assert (decision.reason, decision.held, decision.waiting) == expected[1:]
    else:
        assert isinstance(decision, ts.Halt), decision
        assert (decision.cause, decision.key, decision.stage) == expected[1:]


def test_decide_pick_skips_an_acked_epic_only_at_the_end_of_the_tree():
    empty = _views(others=(_done("1.1"), _done("1.2")), epics=(_epic(CART, "1"),))
    decision = ts.decide_pick(*empty, {}, {}, (), acked=frozenset({CART}))
    assert isinstance(decision, ts.Skip) and decision.reason == ts.SKIP_EMPTY, decision

    gated = _views(
        blocked=(_waits("2.1", CART, epic=CHECKOUT, gated_by=(CART,)),),
        others=(_done("1.1"), _done("1.2")),
    )
    decision = ts.decide_pick(*gated, {}, {}, (), acked=frozenset({CART}))
    assert isinstance(decision, ts.Halt), decision
    assert (decision.cause, decision.key) == (ts.HALT_AWAITING_CLOSURE, CART)


def test_decide_pick_notes_what_it_passed_over():
    next_view, status_view = _views(
        start=(ticket_row("1.1", status="ready-for-dev"), ticket_row("1.3")),
        in_progress=(ticket_row("1.2", status="built"),),
    )
    decision = ts.decide_pick(next_view, status_view, {"1.1": Phase.DEFERRED}, {}, ())
    assert isinstance(decision, ts.Dispatch) and decision.ref == "1.3"
    assert decision.notes == (
        ts.PickNote(ts.NOTE_FOREIGN_ACTIVE, "1.2", "built"),
        ts.PickNote(ts.NOTE_SKIPPED, "1.1", "touched", "deferred"),
    )


def test_backlog_is_never_picked():
    backlog = fake_next_view(
        folder="backlog", ready_to_start=(ticket_row("story-x.md"),)
    )
    next_view, status_view = _views(epics=(_epic(CART, "1", status="done"),))
    next_view = NextView(**{**next_view.__dict__, "backlog": backlog})
    decision = ts.decide_pick(next_view, status_view, {}, {}, ())
    assert decision == ts.Skip(ts.SKIP_EMPTY)


def test_halt_stages_cover_every_cause():
    causes = {
        v for k, v in vars(ts).items() if k.startswith("HALT_") and isinstance(v, str)
    }
    assert set(ts.HALT_STAGES) == causes
    assert set(ts.HALT_STAGES.values()) == {
        PAUSE_TICKET_HITL,
        PAUSE_TICKET_REFINE,
        PAUSE_TICKET_TREE,
        PAUSE_PLAN_CHECKPOINT,
        PAUSE_EPIC_BOUNDARY,
        PAUSE_ESCALATION,
    }


@pytest.mark.parametrize(
    ("fields", "halt_leg"),
    [
        ({"plan_checkpoint": True}, True),
        ({"plan_checkpoint": True, "status": "draft"}, True),
        ({"plan_checkpoint": True, "status": "ready-for-dev"}, False),
        ({"plan_checkpoint": True, "status": "in-progress"}, False),
        ({"plan_checkpoint": True, "refined": True}, False),
        ({}, False),
    ],
)
def test_is_plan_halt_leg(fields, halt_leg):
    assert ts.is_plan_halt_leg(ticket_row("1.1", **fields)) is halt_leg


@pytest.mark.parametrize(
    ("thorough_review", "risk", "want"),
    [
        ("always", "low", True),
        ("high-risk", "high", True),
        ("high-risk", "low", False),
        ("never", "high", False),
    ],
)
def test_wants_thorough(thorough_review, risk, want):
    assert ts.wants_thorough(thorough_review, risk) is want


@pytest.mark.parametrize(
    ("source", "stage", "key", "registered", "approved"),
    [
        ("tickets", PAUSE_PLAN_CHECKPOINT, "1.1", False, "1.1"),
        ("tickets", PAUSE_PLAN_CHECKPOINT, "1.1", True, None),
        ("tickets", PAUSE_TICKET_HITL, "1.1", False, None),
        ("tickets", PAUSE_PLAN_CHECKPOINT, None, False, None),
        ("stories", PAUSE_PLAN_CHECKPOINT, "1", False, None),
    ],
    ids=["refined-pick-pause", "unit-pause", "other-stage", "no-key", "stories-run"],
)
def test_approve_paused_story_file(source, stage, key, registered, approved):
    state = RunState(run_id="r", project_root="/p", source=source)
    state.pause_reason, state.pause_ticket = stage, key
    if registered and key:
        state.task_phases[key] = "dev-running"
    assert ts.approve_paused_story_file(state) == approved
    assert ts.approve_paused_story_file(state) is None
    assert state.ticket_story_approvals == ([approved] if approved else [])


def _boundary(views, closures=None, acked=(), committed=(CART,), resumed=()):
    _, status_view = views
    return [
        (b.action, b.slug, b.verdict)
        for b in ts.epic_boundary(
            status_view,
            closures or {},
            frozenset(acked),
            frozenset(committed),
            resumed=frozenset(resumed),
        )
    ]


@pytest.mark.parametrize(
    ("views", "closures", "acked", "committed", "resumed", "expected"),
    [
        pytest.param(
            _views(others=(_done("1.1"), ticket_row("1.2", status="built"))),
            None,
            (),
            (CART,),
            (),
            [("retro", CART, "")],
            id="finished-and-committed-owes-a-retro",
        ),
        pytest.param(
            _views(others=(_done("1.1"),)),
            None,
            (),
            (),
            (),
            [],
            id="finished-by-someone-else-owes-nothing",
        ),
        pytest.param(
            _views(others=(_done("1.1"), ticket_row("1.2", status="in-review"))),
            None,
            (),
            (CART,),
            (),
            [],
            id="unfinished-owes-nothing",
        ),
        pytest.param(
            _views(others=(_done("1.1"),), epics=(_epic(CART, "1", status="done"),)),
            {CART: "rejected"},
            (),
            (CART,),
            (),
            [],
            id="closed-epic-owes-nothing",
        ),
        pytest.param(
            _views(others=(_done("1.1"),)),
            {CART: "rejected"},
            (),
            (CART,),
            (),
            [("rejected", CART, "rejected")],
            id="rejected-open-and-finished-pauses-again",
        ),
        pytest.param(
            _views(start=(ticket_row("1.3"),), others=(_done("1.1"),)),
            {CART: "rejected"},
            (),
            (CART,),
            (),
            [],
            id="rejected-with-a-fix-up-ticket-builds-it-first",
        ),
        pytest.param(
            _views(others=(_done("1.1"), _done("2.1", epic=CHECKOUT))),
            {CART: "accepted"},
            (),
            (CART, CHECKOUT),
            (CART,),
            [("ack", CART, "accepted"), ("retro", CHECKOUT, "")],
            id="resumed-closure-then-the-next-epic-in-build-order",
        ),
        pytest.param(
            _views(others=(_done("1.1"), _done("2.1", epic=CHECKOUT))),
            {CART: "accepted"},
            (),
            (CART, CHECKOUT),
            (),
            [("pause", CART, "accepted"), ("retro", CHECKOUT, "")],
            id="closure-no-resume-answered-pauses-for-it",
        ),
        pytest.param(
            _views(others=(_done("1.1"),)),
            {CART: "unknown"},
            (CART,),
            (CART,),
            (),
            [],
            id="acked-closure-owes-nothing",
        ),
        pytest.param(
            _views(others=(_done("1.1"),), epics=(_epic(CART, "1"), UNSLICED)),
            {"epic-payment": "accepted"},
            (),
            (CART, "epic-payment"),
            (),
            [("retro", CART, "")],
            id="unsliced-epic-owes-nothing-even-with-a-closure",
        ),
    ],
)
def test_epic_boundary(views, closures, acked, committed, resumed, expected):
    assert _boundary(views, closures, acked, committed, resumed) == expected


@pytest.mark.parametrize(
    ("source", "stage", "key", "closures", "recorded"),
    [
        ("tickets", PAUSE_EPIC_BOUNDARY, CART, {CART: "accepted"}, CART),
        ("tickets", PAUSE_EPIC_BOUNDARY, CART, {CART: "rejected"}, None),
        ("tickets", PAUSE_EPIC_BOUNDARY, CART, {}, None),
        ("tickets", PAUSE_TICKET_HITL, CART, {CART: "accepted"}, None),
        ("tickets", PAUSE_EPIC_BOUNDARY, None, {CART: "accepted"}, None),
        ("stories", PAUSE_EPIC_BOUNDARY, CART, {CART: "accepted"}, None),
    ],
    ids=[
        "closure-pause",
        "rejected",
        "refusal-pause",
        "other-stage",
        "no-key",
        "stories-run",
    ],
)
def test_resume_epic_closure(source, stage, key, closures, recorded):
    state = RunState(run_id="r", project_root="/p", source=source)
    state.pause_reason, state.pause_ticket = stage, key
    state.ticket_epic_closures = dict(closures)
    assert ts.resume_epic_closure(state) == recorded
    assert ts.resume_epic_closure(state) is None
    assert state.ticket_epic_closure_resumed == ([recorded] if recorded else [])


def test_parse_next_roundtrip():
    from bmad_orchestrate.ticketmodel import parse_next

    view = fake_next_view(ready_to_start=(ticket_row("1.1"),))
    doc = {
        "store": view.store,
        "folder": view.folder,
        "ready_to_refine": [],
        "ready_to_start": [
            {
                "ref": "1.1",
                "epic": CART,
                "id": "1",
                "file": None,
                "type": "story",
                "title": "Ticket 1.1",
                "status": "",
                "tracker_status": "",
                "state": "planned",
                "assignee": "",
                "hitl": False,
                "risk": "",
                "refine": False,
                "refined": False,
                "blocked_at": "",
                "blocked_reason": "",
                "after": [],
            }
        ],
        "in_progress": [],
        "blocked": [],
    }
    parsed = parse_next(doc)
    assert parsed.ready_to_start[0].ref == "1.1"
