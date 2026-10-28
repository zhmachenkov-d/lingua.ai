"""BMAD v7 plan status vocabulary used by ticketmodel / decide_pick."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

PLAN_STATUS_ORDER: Final[tuple[str, ...]] = (
    "",
    "draft",
    "ready-for-dev",
    "in-progress",
    "in-review",
    "built",
    "done",
)
PLAN_BLOCKED: Final = "blocked"
PLAN_DROPPED: Final = "dropped"
PLAN_AWAITING_OPERATOR: Final = "awaiting-operator"
OPERATOR_PARK_PREFIX: Final = "awaiting operator: "

PlanWriteReason = Literal[
    "accept", "park", "confirm", "repair", "rearm", "rollback", "replan", "salvage"
]

_BUILD_STATUSES: Final = frozenset(PLAN_STATUS_ORDER[1:6])
_STARTED: Final = frozenset(PLAN_STATUS_ORDER[2:6])


@dataclass(frozen=True)
class PlanRule:
    sources: frozenset[str]
    targets: frozenset[str]
    parked: bool = False


PLAN_TRANSITIONS: Final[dict[PlanWriteReason, PlanRule]] = {
    "accept": PlanRule(frozenset({"built"}), frozenset({"done"})),
    "park": PlanRule(
        _BUILD_STATUSES | {PLAN_AWAITING_OPERATOR}, frozenset({PLAN_BLOCKED}), parked=True
    ),
    "confirm": PlanRule(frozenset(), frozenset({"done", "built"}), parked=True),
    "repair": PlanRule(
        frozenset({"in-progress", "in-review", "built"}), frozenset({"in-progress"})
    ),
    "rearm": PlanRule(
        frozenset({PLAN_BLOCKED, "in-progress", "in-review", "built"}),
        frozenset({"ready-for-dev", "in-progress", "in-review"}),
    ),
    "rollback": PlanRule(_STARTED, frozenset({"ready-for-dev"})),
    "replan": PlanRule(_STARTED | {PLAN_BLOCKED}, frozenset({"draft"})),
    "salvage": PlanRule(frozenset({"in-progress", "in-review"}), frozenset({"built"})),
}
