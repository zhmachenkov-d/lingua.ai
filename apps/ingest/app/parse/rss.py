from __future__ import annotations

import os
import resource
import threading
import time
from dataclasses import dataclass, field


def _cgroup_rss_bytes() -> int | None:
    for path in (
        "/sys/fs/cgroup/memory.current",
        "/sys/fs/cgroup/memory/memory.usage_in_bytes",
    ):
        try:
            raw = open(path, encoding="utf-8").read().strip()
            value = int(raw)
            if value > 0:
                return value
        except (OSError, ValueError):
            continue
    return None


def _proc_self_rss_bytes() -> int | None:
    try:
        with open("/proc/self/status", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    kb = int(line.split()[1])
                    return kb * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def _process_tree_rss_bytes() -> int | None:
    try:
        import psutil

        proc = psutil.Process(os.getpid())
        total = proc.memory_info().rss
        for child in proc.children(recursive=True):
            try:
                total += child.memory_info().rss
            except (psutil.Error, OSError):
                continue
        return total if total > 0 else None
    except Exception:
        return None


def current_rss_bytes() -> int:
    """Best-effort RSS: cgroup → process tree (incl. Marker children) → self."""
    for probe in (
        _cgroup_rss_bytes,
        _process_tree_rss_bytes,
        _proc_self_rss_bytes,
    ):
        value = probe()
        if value is not None and value > 0:
            return value
    try:
        import psutil

        return int(psutil.Process().memory_info().rss)
    except Exception:
        # Linux ru_maxrss is KiB
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)


@dataclass
class PeakRssTracker:
    """Samples RSS on an interval; tracks section peak during each PDF parse."""

    interval_s: float = 0.25
    _peak_bytes: int = 0
    _stop: threading.Event | None = field(default=None, repr=False)
    _thread: threading.Thread | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        seed = current_rss_bytes()
        self._peak_bytes = seed
        self._stop = threading.Event()

    @property
    def peak_bytes(self) -> int:
        return self._peak_bytes

    def observe(self) -> int:
        value = current_rss_bytes()
        if value > self._peak_bytes:
            self._peak_bytes = value
        return value

    def begin_section(self) -> None:
        self._peak_bytes = current_rss_bytes()

    def start(self) -> None:
        assert self._stop is not None
        self.observe()
        self._thread = threading.Thread(
            target=self._sample_loop, name="peak-rss", daemon=True
        )
        self._thread.start()

    def _sample_loop(self) -> None:
        assert self._stop is not None
        while not self._stop.wait(self.interval_s):
            self.observe()

    def stop(self) -> None:
        assert self._stop is not None
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        time.sleep(0)
        self.observe()
