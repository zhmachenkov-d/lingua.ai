from __future__ import annotations

import os
import resource
import threading
import time
from dataclasses import dataclass, field


def _cgroup_rss_mb() -> float | None:
    for path in (
        "/sys/fs/cgroup/memory.current",
        "/sys/fs/cgroup/memory/memory.usage_in_bytes",
    ):
        try:
            raw = open(path, encoding="utf-8").read().strip()
            return int(raw) / 1048576.0
        except (OSError, ValueError):
            continue
    return None


def _proc_self_rss_mb() -> float | None:
    try:
        with open("/proc/self/status", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    kb = int(line.split()[1])
                    return kb / 1024.0
    except (OSError, ValueError, IndexError):
        return None
    return None


def _process_tree_rss_mb() -> float | None:
    try:
        import psutil

        proc = psutil.Process(os.getpid())
        total = proc.memory_info().rss
        for child in proc.children(recursive=True):
            try:
                total += child.memory_info().rss
            except (psutil.Error, OSError):
                continue
        return total / 1048576.0
    except Exception:
        return None


def current_rss_mb() -> float:
    for probe in (_cgroup_rss_mb, _process_tree_rss_mb, _proc_self_rss_mb):
        value = probe()
        if value is not None and value > 0:
            return value
    try:
        import psutil

        return psutil.Process().memory_info().rss / 1048576.0
    except Exception:
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


@dataclass
class PeakRssTracker:
    """Samples RSS on an interval; tracks section peak and job-wide peak."""

    interval_s: float = 0.25
    _peak_mb: float = 0.0
    _job_peak_mb: float = 0.0
    _stop: threading.Event | None = field(default=None, repr=False)
    _thread: threading.Thread | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        seed = current_rss_mb()
        self._peak_mb = seed
        self._job_peak_mb = seed
        self._stop = threading.Event()

    @property
    def peak_mb(self) -> float:
        return self._peak_mb

    @property
    def job_peak_mb(self) -> float:
        return self._job_peak_mb

    def observe(self) -> float:
        value = current_rss_mb()
        if value > self._peak_mb:
            self._peak_mb = value
        if value > self._job_peak_mb:
            self._job_peak_mb = value
        return value

    def begin_section(self) -> None:
        self._peak_mb = current_rss_mb()

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

    def stop(self) -> float:
        assert self._stop is not None
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        time.sleep(0)
        self.observe()
        return self._job_peak_mb
