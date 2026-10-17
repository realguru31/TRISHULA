"""TRISHULA · SPX 0DTE analytics on tastytrade data.

Tabs: TASTIER · AG-REV · VS3D. A background recorder (core/recorder.py)
records the tape and chain while the app is awake and flushes to the
app container's disk every 5 minutes (vs3dgbt-style day state). Keep one
browser tab open on this app (the VPS) so Streamlit Cloud never sleeps it.
"""
import logging

import streamlit as st

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
</style>""", unsafe_allow_html=True)


@st.cache_resource(show_spinner=False)
def get_recorder() -> Recorder:
    s = st.secrets
    r = Recorder(s["TT_CLIENT_SECRET"], s["TT_REFRESH_TOKEN"],
                 s.get("DATA_REPO"), s.get("GH_TOKEN"))
    r.start()
    return r


missing = [k for k in ("TT_CLIENT_SECRET", "TT_REFRESH_TOKEN") if k not in st.secrets]
if missing:
    st.error(f"Missing Streamlit secrets: {', '.join(missing)} — add them in the app's Settings → Secrets.")
    st.stop()

rec = get_recorder()
rec.start()          # restarts the thread if it ever died


@st.fragment(run_every=30)
def status_bar():
    s = rec.status()
    age = s["last_event_age_s"]
    dot = "🟢" if (age is not None and age < 120) else "🟡" if (age is not None and age < 600) else "🔴"
    flush = s["last_flush"][11:19] if s["last_flush"] else "never"
    err = f" · ⚠ flush: {s['flush_error'][:80]}" if s["flush_error"] else ""
    st.caption(f"{dot} {LABEL} · recorder: {s['state']} · prints {s['prints']:,} · "
               f"chain rows {s['chain_rows']:,} · last event "
               f"{'—' if age is None else f'{age:.0f}s ago'} · last flush {flush}{err} · "
               f"{now_et():%a %H:%M:%S} ET")


st.markdown(f"### 🔱 TRISHULA <span style='font-size:0.7em;color:#8b949e'>v{VERSION}</span>", unsafe_allow_html=True)
status_bar()
t1, t2, t3 = st.tabs(["TASTIER", "AG-REV", "VS3D"])
with t1:
    tastier.render(rec)
with t2:
    agrev.render(rec)
with t3:
    vs3d.render(rec)
for t, name in ((t1, "TASTIER"), (t2, "AG-REV"), (t3, "VS3D")):
    t.caption(f"{name} · {LABEL}")

@st.fragment(run_every=30)
def diagnostics():
    with st.expander(f"Recorder diagnostics · {LABEL}"):
        st.json(rec.status())
        for e in list(rec.errors)[-10:][::-1]:
            st.code(f"{e['t']} [{e['where']}] {e['err']}\n{e['tb']}")


diagnostics()
