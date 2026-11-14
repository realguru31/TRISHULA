"""v0.28.0 — expiry identity and expiry TIME for every SPX-family contract.

tastytrade lists every root expiring on a date in one list (SPXW PM, SPX AM monthly, SPXO AM weekly since 9 Nov 2026).
Until v0.27 TRISHULA mixed them and assumed every contract expires at 16:00. Now:
  label   PM (SPXW)  → "YYYY-MM-DD"        (unchanged — the 0DTE/1DTE pipeline, Book, Lean, TASTIER: PM only)
          AM (SPX monthly, SPXO) → "YYYY-MM-DDAM"   (long-dated book / Terrain only)
  end     PM → the chain's stops_trading_at (16:00 ET, 13:00 ET on half days: 27 Nov, 24 Dec 2026)
          AM → 09:30 ET on the date (settles to the SPX opening print; stops trading the prior day at 16:00)
`register(chain)` is called by the recorder each session; `end()` falls back to the rules above for unregistered labels.
"""
from __future__ import annotations

import datetime as dt

_END: dict[str, dt.datetime] = {}            # label → naive ET datetime of expiry
HALF_DAYS = {dt.date(2026, 11, 27), dt.date(2026, 12, 24)}     # fallback only; the chain's stops_trading_at wins
AM_END = dt.time(9, 30)


def is_pm(o) -> bool:
    return str(getattr(o, "settlement_type", "PM") or "PM").upper().startswith("PM")


def label(d, pm: bool) -> str:
    return str(d) if pm else f"{d}AM"


def date_of(es) -> dt.date:
    return dt.date.fromisoformat(str(es)[:10])


def _to_et(ts) -> dt.datetime | None:
    try:
        from zoneinfo import ZoneInfo
        if ts is None:
            return None
        if ts.tzinfo is None:
            return ts
        return ts.astimezone(ZoneInfo("America/New_York")).replace(tzinfo=None)
    except Exception:                                   # noqa: BLE001
        return None


def register(chain) -> None:
    """chain: {date: [Option]} from tastytrade get_option_chain."""
    for d, opts in (chain or {}).items():
        pm = [o for o in opts if is_pm(o)]
        if pm:
            stops = [_to_et(getattr(o, "stops_trading_at", None)) for o in pm[:5]]
            stops = [s_ for s_ in stops if s_ is not None and s_.date() == d]
            _END[label(d, True)] = min(stops) if stops else _fallback(label(d, True))
        if len(pm) < len(opts):
            _END[label(d, False)] = dt.datetime.combine(d, AM_END)


def _fallback(es: str) -> dt.datetime:
    d = date_of(es)
    if str(es).endswith("AM"):
        return dt.datetime.combine(d, AM_END)
    return dt.datetime.combine(d, dt.time(13, 0) if d in HALF_DAYS else dt.time(16, 0))


def end(es) -> dt.datetime:
    """Naive ET datetime when contracts of this label stop counting (expiry / settlement)."""
    es = str(es)
    return _END.get(es) or _fallback(es)


def end_ms(es) -> int:
    from zoneinfo import ZoneInfo
    return int(end(es).replace(tzinfo=ZoneInfo("America/New_York")).timestamp() * 1000)


def root_of(sym: str) -> str:
    s = str(sym).lstrip(".")
    for r in ("SPXW", "SPXO", "SPX"):
        if s.startswith(r):
            return r
    return ""
