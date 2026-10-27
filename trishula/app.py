"""TRISHULA · SPX 0DTE analytics on tastytrade data.

Tabs: TASTIER · AG-REV · VS3D. A background recorder (core/recorder.py)
records the tape and chain while the app is awake and flushes to the
app container's disk every 5 minutes (vs3dgbt-style day state). Keep one
browser tab open on this app (the VPS) so Streamlit Cloud never sleeps it.
"""
import logging

import time

import streamlit as st

from core import loader as LD
from core import mem as MEM
from core.controls import control_bar
from core.player import player_bar, ticker
from core.view import view
from core.recorder import Recorder
from core.timeutil import now_et
from core.version import LABEL, VERSION
from tabs import agrev, tastier, vs3d

logging.getLogger("tastytrade").setLevel(logging.WARNING)

st.set_page_config(page_title=f"TRISHULA v{VERSION}", page_icon="🔱", layout="wide")
st.markdown("""<style>
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"], [class*="viewerBadge"] {display:none !important;}
header[data-testid="stHeader"] {background: transparent;}
.block-container {padding-top: 1rem;}
div[data-testid="stMetricValue"] {font-size: 1.35rem;}
/* tabs: bordered boxes, faint dividers, active = blue top border (Streamlit ≥1.50 react-aria DOM) */
[data-testid="stTabs"] [role="tablist"] {gap:0 !important; border-bottom:1px solid #30363d;}
[data-testid="stTab"] {background:#0b0f14; border:1px solid #30363d; border-bottom:none;
  border-radius:6px 6px 0 0; padding:6px 18px !important; margin-right:-1px; color:#8b949e;}
[data-testid="stTab"]:hover {background:#161b22;}
[data-testid="stTab"][aria-selected="true"] {background:#161b22; border-top:2px solid #1e90ff;}
[data-testid="stTab"][aria-selected="true"] p {color:#ffffff !important; font-weight:600;}
[data-testid="stTab"] p {color:#8b949e;}
[data-testid="stTab"] .react-aria-SelectionIndicator {display:none;}
/* top-level tabs larger than sub-tabs */
[data-testid="stTab"] p {font-size:1.02rem;}
[data-testid="stTabs"] [data-testid="stTabs"] [data-testid="stTab"] {padding:4px 14px !important;}
[data-testid="stTabs"] [data-testid="stTabs"] [data-testid="stTab"] p {font-size:0.88rem !important;}
</style>""", unsafe_allow_html=True)


@st.cache_resource(show_spinner=False)
def get_recorder(version: str) -> Recorder:
    """One recorder per app version. A newer upload stops the older recorder
    (registered in builtins so it survives Streamlit's module reloads)."""
    import builtins
    old = getattr(builtins, "_trishula_recorder", None)
    if old is not None and getattr(old, "version", None) != version and hasattr(old, "stop"):
        old.stop()
    s = st.secrets
    r = Recorder(s["TT_CLIENT_SECRET"], s["TT_REFRESH_TOKEN"],
                 s.get("DATA_REPO"), s.get("GH_TOKEN"))
    builtins._trishula_recorder = r
    r.start()
    return r


def stale_recorders() -> list[str]:
    """Recorder threads from versions that cannot be stopped from here (pre-0.2.1)."""
    import threading
    return [t.name for t in threading.enumerate()
            if t.name.startswith("trishula-recorder") and t.name != f"trishula-recorder-{VERSION}"]


missing = [k for k in ("TT_CLIENT_SECRET", "TT_REFRESH_TOKEN") if k not in st.secrets]
if missing:
    st.error(f"Missing Streamlit secrets: {', '.join(missing)} — add them in the app's Settings → Secrets.")
    st.stop()

rec = get_recorder(VERSION)
rec.start()          # restarts the thread if it ever died


@st.cache_resource(show_spinner=False)
def get_feed(version: str, key: str):
    """v0.20.0: NinjaTrader signals feed (static/dtsignals_<SIGNALS_KEY>.json), one per app version."""
    from core.feed import Feed
    return Feed(rec, key).start()


_fkey = str(st.secrets.get("SIGNALS_KEY", "") or "")
feed = get_feed(VERSION, _fkey) if len(_fkey) >= 16 else None
if feed is not None:
    feed.start()


def _password_gate():
    """v0.20.0: app password from Streamlit secrets (APP_PASSWORD). The recorder and the feed keep running behind it."""
    import hmac
    pw = str(st.secrets.get("APP_PASSWORD", "") or "")
    if not pw or st.session_state.get("_auth_ok"):
        return
    st.markdown("### 🔱 TRISHULA")
    with st.form("login", clear_on_submit=True):
        x = st.text_input("Password", type="password")
        ok = st.form_submit_button("Enter")
    if ok:
        if hmac.compare_digest(x.encode(), pw.encode()):
            st.session_state["_auth_ok"] = True
            st.rerun()
        st.error("Wrong password.")
    st.stop()


_password_gate()
_stale = stale_recorders()
if _stale:
    st.error(f"⚠ An older recorder is still running ({', '.join(_stale)}). "
             "Streamlit → ⋮ → **Reboot app** once to clear it (only needed when upgrading from v0.2.0 or older).")


@st.fragment(run_every=3)
def _watch():
    """Full-page rerun when the recorder becomes ready or a requested expiry arrives,
    so the control bar and tabs never sit on a stale 'loading…'."""
    ss = st.session_state
    if not ss.get("cb_ready") and rec.all_exps:
        st.rerun()
    want = ss.get("cb_waiting")
    if want and want in rec._subscribed:
        ss["cb_waiting"] = None
        st.rerun()


@st.fragment(run_every=30)
def status_bar():
    s = rec.status()
    age = s["last_event_age_s"]
    dot = "🟢" if (age is not None and age < 120) else "🟡" if (age is not None and age < 600) else "🔴"
    flush = s["last_flush"][11:19] if s["last_flush"] else "never"
    err = f" · ⚠ flush: {s['flush_error'][:80]}" if s["flush_error"] else ""
    sd = s.get("seed", {})
    seed = {"pending": "🧬 seed pending", "replaying": f"🧬 seeding… {sd.get('replay_n', 0):,} replayed · "
            f"candle batches {sd.get('candle_batches', 0)}", "done": f"🧬 seed ✓ {sd.get('replay_n', 0):,} replayed · "
            f"{sd.get('candle_legs', 0)} legs candle-filled"}.get(sd.get("state"), "")
    r = MEM.rss_mb()
    mtxt = f" · mem {r:,.0f} MB (peak {max(s.get('rss_peak_mb', 0), r):,.0f})" + (f" ⚠ thinned ×{s['mem_thins']}" if s.get("mem_thins") else "")
    st.caption(f"{dot} {LABEL} · recorder: {s['state']} · {seed} · prints {s['prints']:,} · "
               f"chain rows {s['chain_rows']:,} · last event "
               f"{'—' if age is None else f'{age:.0f}s ago'} · last flush {flush}{err} · "
               f"{now_et():%a %H:%M:%S} ET" + mtxt)


st.markdown(f"### 🔱 TRISHULA <span style='font-size:0.7em;color:#8b949e'>v{VERSION}</span>", unsafe_allow_html=True)
status_bar()
ctl = control_bar(rec)          # common: expiry (0DTE/1DTE/Weekly/Monthly/Other) + strike window
pl = player_bar(rec)            # universal: refresh interval + replay player (all tabs)
v = view(rec, pl["ts_ms"])      # live recorder, or an as-of view at the replay frame
# lazy tabs: only the open tab computes (Streamlit ≥1.50 on_change="rerun" + .open)
t1, t2, t3 = st.tabs(["TASTIER", "AG-REV", "VS3D"], key="main_tab", on_change="rerun")
for t, name, fn in ((t1, "TASTIER", lambda: tastier.render(v, ctl)),
                    (t2, "AG-REV", lambda: agrev.render(v, ctl)),
                    (t3, "VS3D", lambda: vs3d.render(v, ctl, pl["ts_ms"]))):
    if t.open:
        with t:
            LD.begin(name + (" · replay frame" if pl["ts_ms"] else ""))
            _t0 = time.time()
            try:
                fn()
            finally:
                LD.done()
                _sub = st.session_state.get("vs_sub") if name == "VS3D" else None
                rec.ui_state.setdefault("_timings", {})[name + (f" · {_sub}" if _sub else "")] = (
                    round(time.time() - _t0, 2), now_et().strftime("%H:%M:%S"), round(MEM.rss_mb()))
            st.caption(f"{name} · {LABEL}")

def _day_zip() -> bytes:
    """L13: the day's recorded data as a zip of parquet/json (prints with spreadLeg, snapshots, OI, price)."""
    import io
    import json
    import zipfile
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
    return buf.getvalue()


def day_data():
    """Outside any fragment: download buttons inside fragments lose their media file on reruns."""
    with st.expander("📦 Today's data (download for offline analysis)"):
        c1, c2 = st.columns([1, 3])
        if c1.button("📦 prepare today's data", key="dl_prep", help="zip of everything the recorder holds for the day "
                     "(prints with spreadLeg flag, chain snapshots, OI, price paths) — for offline analysis"):
            with st.spinner("building zip…"):
                st.session_state["dl_zip"] = _day_zip()
        if st.session_state.get("dl_zip"):
            c2.download_button(f"⬇ download ({len(st.session_state['dl_zip']) / 1e6:.1f} MB)", st.session_state["dl_zip"],
                               file_name=f"trishula_day_{now_et():%Y%m%d_%H%M}.zip", mime="application/zip", key="dl_zip_btn")


@st.fragment(run_every=30)
def diagnostics():
    with st.expander(f"Recorder diagnostics · {LABEL}"):
        st.json(rec.status())
        if feed is not None:
            st.caption(f"NinjaTrader feed: last write {feed.last_ok:%H:%M:%S} ET · {feed.n_marks} marks"
                       if feed.last_ok else "NinjaTrader feed: not written yet")
            if feed.last_err:
                st.code(f"feed error: {feed.last_err}")
        else:
            st.caption("NinjaTrader feed OFF — add SIGNALS_KEY (≥ 16 characters) to Streamlit secrets")
        tm = rec.ui_state.get("_timings", {})
        if tm:
            st.caption("last run per tab: seconds · at · memory after (MB)")
            st.dataframe([{"tab": k, "s": v[0], "at": v[1], "MB": v[2]} for k, v in sorted(tm.items())], hide_index=True)
        for e in list(rec.errors)[-10:][::-1]:
            st.code(f"{e['t']} [{e['where']}] {e['err']}\n{e['tb']}")


diagnostics()
day_data()
ticker(pl)        # page timer: live refresh every N min, or one replay frame per 1/2/3 s
MEM.trim()        # M1: hand this run's freed chart/table buffers back to the OS
_watch()          # last on the page: control bar has already set cb_ready / cb_waiting
