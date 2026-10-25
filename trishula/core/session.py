"""Session clock: GTH + RTH.

SPX options trade Cboe Global Trading Hours from 20:15 ET the evening before
(Sunday evening for Monday) until 09:15, then RTH 09:30–16:00. With GTH on,
every screen spans prior 20:15 → 16:00 with a dashed line at the 09:30 open;
with GTH off, screens are cut to 09:30–16:00 (the pre-v0.10 behaviour).

L2 (v0.15): the GTH switch is PER VIEWER — gth() reads the calling browser session's own toggle
(st.session_state["pl_gth"]); STATE is only the fallback for code running outside a page run
(the recorder thread), where it is always True.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from .timeutil import ET

STATE = {"gth": True}
GTH_START = dt.time(20, 15)
RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)


def gth() -> bool:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        if get_script_run_ctx() is not None:
            import streamlit as st
            return bool(st.session_state.get("pl_gth", True))
    except Exception:                                   # noqa: BLE001
        pass
    return bool(STATE.get("gth", True))


def open_dt(day: dt.date) -> dt.datetime:
    """Naive ET datetime the session view starts at."""
    if gth():
        return dt.datetime.combine(day - dt.timedelta(days=1), GTH_START)
    return dt.datetime.combine(day, RTH_OPEN)


def close_dt(day: dt.date) -> dt.datetime:
    return dt.datetime.combine(day, RTH_CLOSE)


def rth_open_dt(day: dt.date) -> dt.datetime:
    return dt.datetime.combine(day, RTH_OPEN)


def ms(d: dt.datetime) -> int:
    return int(d.replace(tzinfo=ET).timestamp() * 1000)


def bounds_ms(day: dt.date) -> tuple[int, int]:
    return ms(open_dt(day)), ms(close_dt(day))


def mask(t: pd.Series, day: dt.date) -> pd.Series:
    """Boolean mask for naive-ET timestamps inside the session view."""
    return (t >= open_dt(day)) & (t < close_dt(day))


def is_rth(t: pd.Series, day: dt.date) -> pd.Series:
    return (t >= rth_open_dt(day)) & (t < close_dt(day))


def trading_day_for(now: dt.datetime) -> dt.date:
    """The session a clock time belongs to (GTH view): 20:15 onward → next trading day;
    Friday after the close through Sunday 20:15 → Friday's (completed) session."""
    d, t, wd = now.date(), now.time(), now.weekday()
    if wd == 5:                                            # Saturday
        return d - dt.timedelta(days=1)
    if wd == 6:                                            # Sunday
        return d + dt.timedelta(days=1) if t >= GTH_START else d - dt.timedelta(days=2)
    if t >= GTH_START:
        if wd == 4:                                        # Friday night: no GTH
            return d
        return d + dt.timedelta(days=1)
    return d


def market_state(now: dt.datetime, listed: set[str] | None = None) -> str:
    """v0.19 L39: "RTH" (09:30–16:00 on a trading day) · "GTH" (Cboe overnight 20:15 → 09:30 into a trading day) ·
    "CLOSED" (16:00–20:15, Friday night → Sunday 20:15, holidays). `listed` = SPXW expiry dates (a trading day has one);
    without it, weekdays count as trading days."""
    def trades(d: dt.date) -> bool:
        return d.weekday() < 5 and (not listed or str(d) in listed)
    t, d = now.time(), now.date()
    if trades(d) and dt.time(9, 30) <= t < dt.time(16, 0):
        return "RTH"
    if t >= GTH_START:
        nxt = d + dt.timedelta(days=1)
        return "GTH" if trades(nxt) and d.weekday() != 4 else "CLOSED"
    if t < dt.time(9, 30) and trades(d):
        return "GTH"
    return "CLOSED"
