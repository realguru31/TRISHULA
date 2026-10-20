"""Session clock: GTH + RTH.

SPX options trade Cboe Global Trading Hours from 20:15 ET the evening before
(Sunday evening for Monday) until 09:15, then RTH 09:30–16:00. With GTH on,
every screen spans prior 20:15 → 16:00 with a dashed line at the 09:30 open;
with GTH off, screens are cut to 09:30–16:00 (the pre-v0.10 behaviour).

STATE is set once per page run by the app from the universal bar toggle
(single-user POC: one process-wide flag).
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
