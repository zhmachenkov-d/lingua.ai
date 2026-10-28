"""Run reporting and token usage."""

from __future__ import annotations

import sys
from dataclasses import asdict, dataclass, field
from typing import Any

from .constants import SHUTDOWN_COMPLETED, log


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def add(self, other: TokenUsage | None) -> None:
        if other is None:
            return
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.total_tokens += other.total_tokens
        self.cache_read_tokens += other.cache_read_tokens
        self.cache_write_tokens += other.cache_write_tokens


@dataclass
class UnitReport:
    ref: str
    kind: str  # ticket | retrospective
    plan_status: str | None = None
    outcome: str = "error"
    deferred_count: int = 0
    tokens: dict[str, int] | None = None
    agent_id: str | None = None
    run_id: str | None = None
    pr_url: str | None = None
    reason: str | None = None
    epic: str | None = None


@dataclass
class RunReport:
    units: list[UnitReport] = field(default_factory=list)
    shutdown: str = SHUTDOWN_COMPLETED
    shutdown_detail: str | None = None
    totals: dict[str, Any] = field(default_factory=dict)
    unrefined_bugs: list[dict[str, str]] = field(default_factory=list)
    next_steps: str | None = None

    def add(self, unit: UnitReport) -> None:
        self.units.append(unit)

    def finalize_totals(self) -> None:
        usage = TokenUsage()
        marked_done = 0
        deferred = 0
        retros = 0
        prs: set[str] = set()
        tickets = 0
        for u in self.units:
            if u.kind == "ticket":
                tickets += 1
                if u.outcome == "done":
                    marked_done += 1
            elif u.kind == "retrospective":
                retros += 1
            deferred += u.deferred_count
            if u.tokens:
                usage.add(
                    TokenUsage(
                        input_tokens=u.tokens.get("input_tokens", 0),
                        output_tokens=u.tokens.get("output_tokens", 0),
                        total_tokens=u.tokens.get("total_tokens", 0),
                        cache_read_tokens=u.tokens.get("cache_read_tokens", 0),
                        cache_write_tokens=u.tokens.get("cache_write_tokens", 0),
                    )
                )
            if u.pr_url:
                prs.add(u.pr_url)
        self.totals = {
            "tickets": tickets,
            "marked_done": marked_done,
            "deferred_items": deferred,
            "retrospectives": retros,
            "prs": len(prs),
            "tokens": {
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "total_tokens": usage.total_tokens,
                "cache_read_tokens": usage.cache_read_tokens,
                "cache_write_tokens": usage.cache_write_tokens,
            },
        }

    def to_dict(self) -> dict[str, Any]:
        self.finalize_totals()
        out: dict[str, Any] = {
            "shutdown": self.shutdown,
            "shutdown_detail": self.shutdown_detail,
            "units": [asdict(u) for u in self.units],
            "unrefined_bugs": list(self.unrefined_bugs),
            "totals": self.totals,
        }
        if self.next_steps:
            out["next_steps"] = self.next_steps
        return out

    def format_human(self) -> str:
        self.finalize_totals()
        detail = f" — {self.shutdown_detail}" if self.shutdown_detail else ""
        lines: list[str] = [
            "=== BMAD factory report ===",
            f"Shutdown: {self.shutdown}{detail}",
        ]
        tickets = [u for u in self.units if u.kind == "ticket"]
        retros = [u for u in self.units if u.kind == "retrospective"]
        lines.append("Tickets:")
        if not tickets:
            lines.append("  (none)")
        for u in tickets:
            tok = u.tokens["total_tokens"] if u.tokens else "null"
            extra = ""
            if u.outcome == "blocked" and u.reason:
                extra = f"  reason={u.reason}"
            elif u.pr_url:
                extra = f"  pr={u.pr_url}"
            elif u.reason:
                extra = f"  reason={u.reason}"
            lines.append(
                f"  {u.ref:<40} {u.outcome:<12} tokens={tok}  deferred={u.deferred_count}{extra}"
            )
        lines.append("Unrefined bugs:")
        if not self.unrefined_bugs:
            lines.append("  none")
        else:
            for bug in self.unrefined_bugs:
                title = bug.get("title") or ""
                suffix = f"  {title}" if title else ""
                lines.append(f"  {bug.get('ref', '?')}{suffix}")
        lines.append("Retrospectives:")
        if not retros:
            lines.append("  none")
        else:
            for u in retros:
                tok = u.tokens["total_tokens"] if u.tokens else "null"
                extra = f"  pr={u.pr_url}" if u.pr_url else ""
                lines.append(f"  {u.ref:<40} {u.outcome:<12} tokens={tok}{extra}")
        t = self.totals
        tok = t["tokens"]
        cache_bits = ""
        cache_read = int(tok.get("cache_read_tokens") or 0)
        cache_write = int(tok.get("cache_write_tokens") or 0)
        if cache_read or cache_write:
            cache_bits = f"  cache_read={cache_read} cache_write={cache_write}"
        lines.append(
            f"Totals: tickets={t['tickets']}  done={t['marked_done']}  "
            f"tokens={tok['total_tokens']}  (in={tok['input_tokens']} out={tok['output_tokens']})"
            f"{cache_bits}  "
            f"deferred={t['deferred_items']}  retros={t['retrospectives']}  prs={t['prs']}  "
            f"unrefined_bugs={len(self.unrefined_bugs)}"
        )
        if self.next_steps:
            lines.append("")
            lines.append(self.next_steps.rstrip())
        return "\n".join(lines) + "\n"

    def print_human(self, stream=sys.stderr) -> None:
        print(self.format_human(), end="", file=stream)


def format_token_cost(usage: TokenUsage | None) -> str:
    if usage is None:
        return "tokens=null"
    parts = [
        f"tokens in={usage.input_tokens} out={usage.output_tokens} "
        f"total={usage.total_tokens}"
    ]
    if usage.cache_read_tokens or usage.cache_write_tokens:
        parts.append(
            f"cache_read={usage.cache_read_tokens} cache_write={usage.cache_write_tokens}"
        )
    return " ".join(parts)


def format_token_cost_from_report(report: RunReport) -> str:
    report.finalize_totals()
    tok = report.totals.get("tokens") or {}
    parts = [
        f"tokens in={tok.get('input_tokens', 0)} out={tok.get('output_tokens', 0)} "
        f"total={tok.get('total_tokens', 0)}"
    ]
    cache_read = int(tok.get("cache_read_tokens") or 0)
    cache_write = int(tok.get("cache_write_tokens") or 0)
    if cache_read or cache_write:
        parts.append(f"cache_read={cache_read} cache_write={cache_write}")
    return " ".join(parts)


def log_cumulative_tokens(report: RunReport) -> None:
    log.info("token cost cumulative %s", format_token_cost_from_report(report))
