"""Universal bar above the tabs: screen refresh (R1) + replay player (R2).

Modes are implicit: ⏸ while live freezes at the latest frame (player mode),
▶ steps one frame per 1/2/3 s, ⏮ jumps to the first frame paused, dragging
the scrubber jumps there paused, ⏹ LIVE returns to live data. Every tab
renders as of the returned ts_ms (None = live).
"""
from __future__ import annotations

import datetime as dt

import streamlit as st

from .timeutil import ET
from .view import frames


def _lbl(t):
    return dt.datetime.fromtimestamp(t / 1000, ET).strftime("%a %H:%M")


def player_bar(rec) -> dict:
    ss = st.session_state
    ss.setdefault("pl_mode", "live")          # live | replay
    ss.setdefault("pl_play", False)
    ss.setdefault("pl_idx", 0)
    fr = frames(rec)
    n = len(fr)
    if n:
        ss["pl_idx"] = max(0, min(int(ss["pl_idx"]), n - 1))

    def _first():
        ss.update(pl_mode="replay", pl_play=False, pl_idx=0)

    def _play():
        if ss["pl_mode"] == "live":
            ss["pl_idx"] = 0
        ss.update(pl_mode="replay", pl_play=True)

    def _pause():
        if ss["pl_mode"] == "live":
            ss["pl_idx"] = max(0, n - 1)
        ss.update(pl_mode="replay", pl_play=False)

    def _live():
        ss.update(pl_mode="live", pl_play=False)

    def _scrub():
        t = ss.get("pl_scrub")
        if t in fr:
            ss.update(pl_mode="replay", pl_play=False, pl_idx=fr.index(t))

    live = ss["pl_mode"] == "live" or not n
    with st.container(border=True):
        c = st.columns([1.15, 0.42, 0.42, 0.42, 0.62, 1.05, 3.6, 1.6])
        if live:
            c[0].markdown("<div style='padding-top:.45rem;font-weight:700;color:#ff4d4d'>🔴 LIVE</div>",
                          unsafe_allow_html=True)
        else:
            t = fr[ss["pl_idx"]]
            c[0].markdown(f"<div style='padding-top:.45rem;font-weight:700;color:#58a6ff'>"
                          f"{'▶' if ss['pl_play'] else '⏸'} REPLAY {_lbl(t)}</div>", unsafe_allow_html=True)
        c[1].button("⏮", key="pl_b_first", on_click=_first, disabled=not n, help="first frame (paused)")
        c[2].button("▶", key="pl_b_play", on_click=_play, disabled=not n, help="play")
        c[3].button("⏸", key="pl_b_pause", on_click=_pause, disabled=not n, help="pause — freeze here (player mode)")
        c[4].button("⏹ LIVE", key="pl_b_live", on_click=_live, help="stop replay, back to live data")
        c[5].segmented_control("speed", ["1 s", "2 s", "3 s"], default="1 s", key="pl_speed",
                               label_visibility="collapsed", help="seconds per frame")
        if n > 1:
            cur = fr[ss["pl_idx"]] if not live else fr[-1]
            ss["pl_scrub"] = cur
            c[6].select_slider("frame", options=fr, key="pl_scrub", on_change=_scrub,
                               format_func=_lbl, label_visibility="collapsed")
        else:
            c[6].caption("replay frames appear as the recorder stores chain snapshots (every 60 s in session)")
        c[7].select_slider("refresh", options=list(range(1, 11)), value=5, key="pl_refresh",
                           format_func=lambda m: f"refresh {m} min", label_visibility="collapsed",
                           help="screen refresh while LIVE (snapshots are still recorded every 60 s)")
    speed = {"1 s": 1, "2 s": 2, "3 s": 3}.get(ss.get("pl_speed") or "1 s", 1)
    if live:
        return {"ts_ms": None, "mode": "live", "run_every": int(ss.get("pl_refresh", 5)) * 60, "frames": fr}
    return {"ts_ms": fr[ss["pl_idx"]], "mode": "replay", "run_every": speed if ss["pl_play"] else None,
            "frames": fr, "idx": ss["pl_idx"]}


def ticker(pl: dict):
    """One timer for the whole page: live → full refresh every N min; playing →
    advance one frame per tick and rerun; paused → no timer."""
    import time
    st.session_state["pl_run_t"] = time.time()          # set on every full-page run

    @st.fragment(run_every=pl["run_every"])
    def _tick():
        ss = st.session_state
        every = pl["run_every"]
        if not every or time.time() - ss.get("pl_run_t", 0) < 0.6 * every:
            return                                   # inline run during the full page run
        if pl["mode"] == "replay" and ss.get("pl_play"):
            n = len(pl["frames"])
            if ss["pl_idx"] >= n - 1:
                ss["pl_play"] = False
            else:
                ss["pl_idx"] = ss["pl_idx"] + 1
        st.rerun(scope="app")
    _tick()
