"""L1 loading indicator: a progress bar with a stage label at the top of the open tab
while it computes, so the screen never sits blank and then pops in all at once.

app.py opens one per tab run (begin); builders call stage("terrain", 0.6) as they go;
done() removes it. stage() is a no-op when no bar is open.
"""
from __future__ import annotations

import time

import streamlit as st

_CUR: dict = {}


def begin(label: str):
    ph = st.empty()
    _CUR.update(ph=ph, label=label, t=time.time(), pct=0.02)
    ph.progress(0.02, text=f"⏳ {label} · starting…")


def stage(text: str, pct: float | None = None):
    ph = _CUR.get("ph")
    if ph is None:
        return
    p = float(pct) if pct is not None else min(0.95, _CUR.get("pct", 0.0) + 0.12)
    p = max(_CUR.get("pct", 0.0), min(0.98, p))
    _CUR["pct"] = p
    try:
        ph.progress(p, text=f"⏳ {_CUR['label']} · {text} · {time.time() - _CUR['t']:.1f}s")
    except Exception:                       # noqa: BLE001 — never break a tab over the loader
        pass


def done():
    ph = _CUR.pop("ph", None)
    _CUR.clear()
    if ph is not None:
        try:
            ph.empty()
        except Exception:                   # noqa: BLE001
            pass
