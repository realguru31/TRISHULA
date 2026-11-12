"""v0.27.1 — the day's recording → GitHub Release asset on the app's own repo, so it can be pulled for offline analysis.

  where   release `data-YYYY-MM-DD` (tag on the trishula-state branch — Streamlit only runs `main`, a tag never
          redeploys the app; release files are not in the git history, so the repo does not grow)
  what    the same zip as "📦 prepare today's data" (prints with spreadLeg, chain snapshots, spot, ES, candles, OI log,
          legs, status, lean minutes) — asset name trishula_day_<YYYYMMDD>_<HHMM>.zip (<HHMM> = ET at the send;
          the automatic one after the close is ..._close.zip)
  when    automatically once a day at 16:05–16:14 ET (before the 16:15 roll moves the recorder to the next expiry)
          + the 📤 button for a mid-session copy
  keep    the newest KEEP_DAYS data releases; older ones (and their tags) are deleted after every send
  token   GITHUB_STATE_TOKEN (fine-grained, this repo only, Contents read/write — covers releases). No token → off.
Never raises into the app; status in `status`.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import threading
import time
import zipfile

from . import state as ST

status: dict = {"last": None, "error": None, "auto_done": None, "pruned": None}
KEEP_DAYS = 10            # data releases kept on GitHub (older ones + their tags are deleted after each send)
_busy = threading.Lock()
AUTO_FROM, AUTO_TO = dt.time(16, 5), dt.time(16, 14)


def day_zip(rec) -> bytes:
    """L13: the day's recorded data as a zip of parquet/json (prints with spreadLeg, snapshots, OI, price)."""
    import pandas as pd
    buf = io.BytesIO()
    parts = {"prints.parquet": lambda: rec.prints_df(), "chain_snapshots.parquet": lambda: rec.chain_df(),
             "spot.parquet": lambda: rec.spot_df(), "es1m.parquet": lambda: rec.es_df(),
             "candles5.parquet": lambda: rec.candles5_df(), "spx1m.parquet": lambda: rec.candles_df(),
             "opt1m_backfill.parquet": lambda: rec.opt1m_df(),          # L22: the ridges' pre-restart source
             "dt2_scorecard.parquet": lambda: (pd.concat(list(rec.ui_state.get("_dt2_cards", {}).values()), ignore_index=True)
                                               if rec.ui_state.get("_dt2_cards") else None),   # v0.17: DT v2 signals + outcomes
             "signals_card.parquet": lambda: (pd.concat(list(rec.ui_state.get("_sig_cards", {}).values()), ignore_index=True)
                                              if rec.ui_state.get("_sig_cards") else None)}   # v0.18: Signals view marks + outcomes
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, fn in parts.items():
            try:
                df = fn()
                if df is not None and len(df):
                    b = io.BytesIO()
                    df.to_parquet(b)
                    z.writestr(name, b.getvalue())
            except Exception as e:                       # noqa: BLE001
                z.writestr(name + ".error.txt", f"{type(e).__name__}: {e}")
        with rec.lock:
            oi = {k: dict(v) for k, v in rec.oi_log.items()}
            legs = {k: list(v) for k, v in rec.legs.items()}
        z.writestr("oi_log.json", json.dumps(oi))
        z.writestr("legs.json", json.dumps(legs))
        z.writestr("status.json", json.dumps(rec.status(), default=str))
        try:                                             # v0.24.0: lean minutes (single-leg + all, 0DTE/1DTE, $M Δ) + SPX 1m
            from . import lean as LN
            z.writestr("lean_minutes.json", json.dumps(LN.live_day(rec) or {}, default=float))
        except Exception as e:                           # noqa: BLE001
            z.writestr("lean_minutes.error.txt", f"{type(e).__name__}: {e}")
    return buf.getvalue()


def _release(day: str) -> dict:
    """The release for `day` (created on first use, tagged on the state branch, pre-release, never 'latest')."""
    tag = f"data-{day}"
    r = ST._api("GET", f"/releases/tags/{tag}")
    if r.status_code == 200:
        return r.json()
    ST._ensure_branch()
    r = ST._api("POST", "/releases", json={"tag_name": tag, "target_commitish": ST.BRANCH, "name": f"TRISHULA data {day}",
                                          "body": "Recorded session data (core/ship.py). Not a code release.",
                                          "prerelease": True, "make_latest": "false"})
    if r.status_code == 422:                             # created meanwhile
        r = ST._api("GET", f"/releases/tags/{tag}")
    r.raise_for_status()
    return r.json()


def _prune(keep: int = KEEP_DAYS) -> None:
    """Delete data-* releases (and their tags) beyond the newest `keep` days. Code is never touched."""
    rels = []
    for page in (1, 2, 3):
        r = ST._api("GET", "/releases", params={"per_page": 100, "page": page})
        r.raise_for_status()
        j = r.json()
        rels += [x for x in j if str(x.get("tag_name", "")).startswith("data-")]
        if len(j) < 100:
            break
    rels.sort(key=lambda x: x["tag_name"], reverse=True)          # data-YYYY-MM-DD sorts by date
    gone = []
    for x in rels[keep:]:
        ST._api("DELETE", f"/releases/{x['id']}")
        ST._api("DELETE", f"/git/refs/tags/{x['tag_name']}")
        gone.append(x["tag_name"][5:])
    status["pruned"] = f"kept {min(len(rels), keep)} day(s)" + (f", deleted {', '.join(gone)}" if gone else "")


def send(rec, label: str | None = None) -> str:
    """Zip the day and upload it. Returns the asset name. Raises on failure (callers catch)."""
    import requests
    from .timeutil import now_et
    if not ST._cfg["token"]:
        raise RuntimeError("GITHUB_STATE_TOKEN not set")
    if not _busy.acquire(blocking=False):
        raise RuntimeError("a send is already running")
    try:
        n = now_et()
        day = str(rec.exps[0]) if rec.exps else n.strftime("%Y-%m-%d")
        name = f"trishula_day_{day.replace('-', '')}_{label or n.strftime('%H%M')}.zip"
        data = day_zip(rec)
        rel = _release(day)
        for a in rel.get("assets", []):                  # same name → replace
            if a.get("name") == name:
                ST._api("DELETE", f"/releases/assets/{a['id']}")
        up = f"https://uploads.github.com/repos/{ST._cfg['repo']}/releases/{rel['id']}/assets"
        h = dict(ST._h(), **{"Content-Type": "application/zip"})
        r = requests.post(up, params={"name": name}, headers=h, data=data, timeout=300)
        r.raise_for_status()
        status["last"] = f"{n:%H:%M} ET · {name} · {len(data) / 1e6:.1f} MB"
        status["error"] = None
        try:
            _prune()
        except Exception as e:                           # noqa: BLE001
            status["pruned"] = f"prune failed: {type(e).__name__}: {str(e)[:80]}"
        return name
    except Exception as e:                               # noqa: BLE001
        status["error"] = f"{type(e).__name__}: {str(e)[:160]}"
        raise
    finally:
        _busy.release()


class AutoShip:
    """Background thread: once per trading day between 16:05 and 16:14 ET, send the day as ..._close.zip."""

    def __init__(self, rec):
        self.rec = rec
        self.t = None

    def start(self):
        if self.t is None or not self.t.is_alive():
            self.t = threading.Thread(target=self._run, daemon=True, name="trishula-ship")
            self.t.start()
        return self

    def _run(self):
        from .timeutil import now_et
        while True:
            try:
                n = now_et()
                today = n.strftime("%Y-%m-%d")
                live = bool(self.rec.exps) and str(self.rec.exps[0]) == today
                if (ST._cfg["token"] and live and n.weekday() < 5 and AUTO_FROM <= n.time() <= AUTO_TO
                        and status.get("auto_done") != today):
                    try:
                        send(self.rec, "close")
                        status["auto_done"] = today
                    except Exception:                    # noqa: BLE001 — retried next minute until 16:14
                        pass
            except Exception:                            # noqa: BLE001
                pass
            time.sleep(60)
