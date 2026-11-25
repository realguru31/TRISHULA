"""v0.27.1 — the day's recording → GitHub Release asset on the app's own repo, so it can be pulled for offline analysis.

  where   release `data-YYYY-MM-DD` (tag on the trishula-state branch — Streamlit only runs `main`, a tag never
          redeploys the app; release files are not in the git history, so the repo does not grow)
  what    the same zip as "📦 prepare today's data" (prints with spreadLeg, chain snapshots, spot, ES, candles, OI log,
          legs, status, lean minutes) — asset name trishula_day_<YYYYMMDD>_<HHMM>.zip (<HHMM> = ET at the send;
          the automatic one after the close is ..._close.zip)
  when    automatically at 12:00, 14:00 and 16:05 ET (v0.37.0 safety copies; the close copy replaces them)
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
# v0.37.0: safety copies during the day + the close; each retried every minute inside its window. The close copy
# replaces the day's intraday copies once it is up. Every attempt is logged to state/ship_log.json on the state branch
# (survives a container restart, so a failed send can be diagnosed).
SLOTS = [(dt.time(12, 0), dt.time(12, 14), "1200"), (dt.time(14, 0), dt.time(14, 14), "1400"),
         (dt.time(15, 30), dt.time(15, 44), "1530"),    # v0.41.2: a late kill (23 Nov) still leaves most of the day
         (AUTO_FROM, AUTO_TO, "close"),
         (dt.time(16, 11), AUTO_TO, "close#2")]    # re-send: the final copy is always from the CURRENT recorder
                                                   # (an older version's shipper still running may send at 16:05)
LOG_PATH = "state/ship_log.json"
_log: list = []


def _note(day: str, label: str, ok: bool, msg: str) -> None:
    from .timeutil import now_et
    _log.append({"t": now_et().strftime("%Y-%m-%d %H:%M:%S"), "day": day, "slot": label, "ok": ok, "msg": msg[:200]})
    del _log[:-40]
    try:
        ST.save_file(LOG_PATH, {"log": _log}, f"ship {day} {label} {'ok' if ok else 'FAILED'}")
    except Exception:                                    # noqa: BLE001
        pass


def _drop_intraday(day: str, keep_name: str) -> None:
    """After the close copy is up, delete that day's intraday copies (…_1200 / …_1400 / manual) to save space."""
    rel = _release(day)
    for a in rel.get("assets", []):
        if a.get("name") != keep_name and a.get("name", "").startswith("trishula_day_"):
            ST._api("DELETE", f"/releases/assets/{a['id']}")


def _parts(rec):
    import pandas as pd
    return {"prints.parquet": lambda: rec.prints_df(), "chain_snapshots.parquet": lambda: rec.chain_df(),
            "spot.parquet": lambda: rec.spot_df(), "es1m.parquet": lambda: rec.es_df(),
            "candles5.parquet": lambda: rec.candles5_df(), "spx1m.parquet": lambda: rec.candles_df(),
            "opt1m_backfill.parquet": lambda: rec.opt1m_df(),
            "x_es_prints.parquet": lambda: (rec.xprints_df("ES") if hasattr(rec, "xprints_df") else None),   # v0.40.0
            "x_spy_prints.parquet": lambda: (rec.xprints_df("SPY") if hasattr(rec, "xprints_df") else None),
            "book.parquet": lambda: (rec.book_frame() if hasattr(rec, "book_frame") else None),  # v0.32.1: long-dated
            # book (all subscribed expiries beyond 0/1DTE) as at the send — OI is fixed for the day
            "dt2_scorecard.parquet": lambda: (pd.concat(list(rec.ui_state.get("_dt2_cards", {}).values()), ignore_index=True)
                                              if rec.ui_state.get("_dt2_cards") else None),   # v0.17
            "signals_card.parquet": lambda: (pd.concat(list(rec.ui_state.get("_sig_cards", {}).values()), ignore_index=True)
                                             if rec.ui_state.get("_sig_cards") else None)}   # v0.18


def _write_parquet(df, path: str, rows: int = 200_000) -> None:
    """v0.42.6: parquet straight to disk in slices — the Arrow copy is one slice, not the whole table."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    w = None
    try:
        for i in range(0, len(df), rows):
            t = pa.Table.from_pandas(df.iloc[i:i + rows], preserve_index=False)
            if w is None:
                w = pq.ParquetWriter(path, t.schema)
            elif t.schema != w.schema:
                t = t.cast(w.schema, safe=False)
            w.write_table(t)
            del t
    finally:
        if w is not None:
            w.close()


def day_zip_file(rec, path: str) -> int:
    """v0.42.6: the day's data written as a zip FILE on disk, one part at a time (was: whole zip + every parquet in
    memory at once → +several hundred MB at 1.3M prints; 23 / 24 Nov the app died right after the 14:00 copy).
    Returns the file size."""
    import gc
    import os
    import tempfile
    from . import mem as MEM
    tmp = tempfile.mkdtemp(prefix="tri_zip_")
    try:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
            for name, fn in _parts(rec).items():
                fp = os.path.join(tmp, name)
                try:
                    df = fn()
                    if df is not None and len(df):
                        _write_parquet(df, fp)
                        del df
                        z.write(fp, name)
                except Exception as e:                   # noqa: BLE001
                    z.writestr(name + ".error.txt", f"{type(e).__name__}: {e}")
                finally:
                    try:
                        os.remove(fp)
                    except OSError:
                        pass
                    gc.collect()
                    try:
                        MEM.trim(0)
                    except Exception:                    # noqa: BLE001
                        pass
            with rec.lock:
                oi = {k: dict(v) for k, v in rec.oi_log.items()}
                legs = {k: list(v) for k, v in rec.legs.items()}
            z.writestr("oi_log.json", json.dumps(oi))
            z.writestr("legs.json", json.dumps(legs))
            del oi, legs
            z.writestr("status.json", json.dumps(rec.status(), default=str))
            z.writestr("book_state.json", json.dumps(getattr(rec, "book_state", {}) or {}, default=str))
            try:                                         # v0.29.0: SPX BB edge series + alerts
                trk = getattr(rec, "_bb", None)
                if trk is not None:
                    z.writestr("spx_bb.json", json.dumps({"series": trk.series, "alerts": trk.alerts, "cfg": trk.cfg},
                                                         default=str))
            except Exception as e:                       # noqa: BLE001
                z.writestr("spx_bb.error.txt", f"{type(e).__name__}: {e}")
            try:                                         # v0.24.0: lean minutes + SPX 1m
                from . import lean as LN
                z.writestr("lean_minutes.json", json.dumps(LN.live_day(rec) or {}, default=float))
            except Exception as e:                       # noqa: BLE001
                z.writestr("lean_minutes.error.txt", f"{type(e).__name__}: {e}")
        return os.path.getsize(path)
    finally:
        try:
            os.rmdir(tmp)
        except OSError:
            pass


def day_zip(rec) -> bytes:
    """Bytes of the day zip (the 📦 download button). Built on disk first (v0.42.6), then read once."""
    import os
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    try:
        day_zip_file(rec, path)
        with open(path, "rb") as f:
            return f.read()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


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
        import os
        import tempfile
        from . import mem as MEM
        try:                                             # v0.42.6: high memory → thin first, then build
            if MEM.rss_mb() > MEM.SOFT_MB and hasattr(rec, "_mem_guard"):
                rec._mem_guard()
        except Exception:                                # noqa: BLE001
            pass
        fd, path = tempfile.mkstemp(suffix=".zip")
        os.close(fd)
        try:
            size = day_zip_file(rec, path)               # on disk, one part at a time
            rel = _release(day)
            for a in rel.get("assets", []):              # same name → replace
                if a.get("name") == name:
                    ST._api("DELETE", f"/releases/assets/{a['id']}")
            up = f"https://uploads.github.com/repos/{ST._cfg['repo']}/releases/{rel['id']}/assets"
            h = dict(ST._h(), **{"Content-Type": "application/zip", "Content-Length": str(size)})
            with open(path, "rb") as f:                  # streamed from disk, not held in memory
                r = requests.post(up, params={"name": name}, headers=h, data=f, timeout=600)
            r.raise_for_status()
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        status["last"] = f"{n:%H:%M} ET · {name} · {size / 1e6:.1f} MB"
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
        done: set = set()                                # (day, label) sent by this container
        while True:
            try:
                n = now_et()
                today = n.strftime("%Y-%m-%d")
                live = bool(self.rec.exps) and str(self.rec.exps[0]) == today
                if ST._cfg["token"] and live and n.weekday() < 5:
                    for a, b, label in SLOTS:
                        if not (a <= n.time() <= b) or (today, label) in done:
                            continue
                        try:
                            name = send(self.rec, label.split("#")[0])
                            done.add((today, label))
                            if label.startswith("close"):
                                status["auto_done"] = today
                                try:
                                    _drop_intraday(today, name)
                                except Exception:        # noqa: BLE001
                                    pass
                                if (today, "unusual") not in done:     # v0.44.0: unusual-flag baseline + score
                                    try:
                                        from . import unusual as UN
                                        if UN.save_day(self.rec, today):
                                            done.add((today, "unusual"))
                                    except Exception:    # noqa: BLE001
                                        pass
                            _note(today, label, True, status.get("last") or name)
                        except Exception as e:           # noqa: BLE001 — retried next minute inside the window
                            _note(today, label, False, f"{type(e).__name__}: {e}")
            except Exception:                            # noqa: BLE001
                pass
            time.sleep(60)
