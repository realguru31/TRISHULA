"""M1 memory hygiene: RSS readout, returning freed heap to the OS, and a guard that
thins old chain snapshots before the container's memory limit kills the app.

Streamlit Community Cloud kills the whole process (no traceback) when it runs out of
memory — the 19 Oct 14:37 crash. The cause was found and fixed in v0.11.1 (plotly
charts carrying one point per print); this module is the safety net.
"""
from __future__ import annotations

import ctypes
import gc
import os
import time

SOFT_MB = 1800          # above this: thin chain snapshots older than 90 min to 5-min spacing
_libc = None
_last_trim = [0.0]


def rss_mb() -> float:
    try:
        with open("/proc/self/statm") as f:
            return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 2**20
    except Exception:                       # noqa: BLE001
        return float("nan")


def trim(min_gap_s: float = 20.0) -> None:
    """gc + glibc malloc_trim: hand freed pandas/plotly buffers back to the OS."""
    global _libc
    if time.time() - _last_trim[0] < min_gap_s:
        return
    _last_trim[0] = time.time()
    gc.collect()
    try:
        if _libc is None:
            _libc = ctypes.CDLL("libc.so.6")
        _libc.malloc_trim(0)
    except Exception:                       # noqa: BLE001
        pass


def thin_snapshots(frames, keep_recent_ms: int = 90 * 60_000, step_ms: int = 5 * 60_000) -> int:
    """Keep every snapshot from the last 90 min, one per 5 min before that. Returns rows dropped."""
    import pandas as pd
    if not frames.chunks:
        return 0
    d = pd.concat(frames.chunks, ignore_index=True)
    if d.empty or "ts_ms" not in d:
        return 0
    t = d["ts_ms"]
    cut = int(t.max()) - keep_recent_ms
    ts = pd.Series(sorted(t[t < cut].unique()))
    keep_old = set(ts.groupby(ts // step_ms).first()) if len(ts) else set()
    m = (t >= cut) | t.isin(keep_old)
    n0 = len(d)
    frames.chunks = [d[m].reset_index(drop=True)]
    frames._cache = None
    return n0 - int(m.sum())
