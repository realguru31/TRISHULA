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

SOFT_MB = 1400          # above this: thin chain snapshots older than 90 min to 5-min spacing
HARD_MB = 1800          # above this also: fold old non-front-expiry prints into per-minute rows (v0.18.0)
_libc = None
_last_trim = [0.0]


_tuned = [False]


def tune() -> bool:
    """v0.21.2: glibc malloc settings for a long-running, multi-threaded pandas process. Measured 27 Oct: the feed
    build (≈1 GB transient) left RSS ~700 MB higher until malloc_trim — freed blocks stay in per-thread arenas and the
    DYNAMIC mmap threshold grows so big column arrays land in the heap. Fix: ≤2 arenas, FIXED 1 MB mmap threshold
    (big arrays are mmapped and returned to the OS the moment they are freed), trim the heap top above 32 MB."""
    global _libc
    if _tuned[0]:
        return True
    try:
        if _libc is None:
            _libc = ctypes.CDLL("libc.so.6")
        _libc.mallopt(-8, 2)              # M_ARENA_MAX
        _libc.mallopt(-3, 1 << 20)        # M_MMAP_THRESHOLD (fixing it also disables the dynamic growth)
        _libc.mallopt(-1, 32 << 20)       # M_TRIM_THRESHOLD
        _tuned[0] = True
    except Exception:                       # noqa: BLE001
        pass
    return _tuned[0]


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


def fold_prints(df, front: str, older_than_ms: int):
    """Fold prints of expiries other than `front` older than the cut into one row per
    contract × minute × side (size summed, price = size-weighted). Keeps per-minute volume and
    the bought/sold split that ridges, Tetris and DT use; drops per-print detail. Returns (df, rows saved)."""
    import numpy as np
    import pandas as pd
    if df is None or df.empty or "exp" not in df:
        return df, 0
    old = (df["exp"].astype(str) != front) & (df["ts_ms"] < older_than_ms)
    if not old.any():
        return df, 0
    o = df[old].copy()
    o["ts_ms"] = (o["ts_ms"] // 60_000) * 60_000
    o["_pxs"] = o["px"] * o["size"]
    keys = [c for c in ("sym", "ts_ms", "aggr", "aggr_side", "bucket", "spread_leg", "ev_type") if c in o]
    agg = {c: "first" for c in o.columns if c not in keys + ["size", "_pxs"]}
    agg.update(size="sum", _pxs="sum")
    g = o.groupby(keys, observed=True, dropna=False, sort=False).agg(agg).reset_index()
    g["px"] = np.where(g["size"] > 0, g["_pxs"] / g["size"].where(g["size"] > 0, 1), g["px"])
    g = g.drop(columns="_pxs")
    g["idx"] = -np.arange(1, len(g) + 1, dtype=np.int64) - int(older_than_ms // 1000) * 10_000
    if "src" in g:
        g["src"] = "folded"
    out = pd.concat([g[df.columns], df[~old]], ignore_index=True).sort_values("ts_ms", kind="stable", ignore_index=True)
    return out, int(old.sum()) - len(g)
