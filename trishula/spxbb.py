"""SPX BB · standalone app (v0.36.0) — point a second Streamlit Cloud app at trishula/spxbb.py.

Its own slim tastytrade feed (core/bbfeed.py), the SPX BB tracker + Telegram alerts (core/bb.py) and the tab
(tabs/spxbb.py). Same Streamlit secrets as TRISHULA (copied, nothing new): TT_CLIENT_SECRET, TT_REFRESH_TOKEN,
APP_PASSWORD, TG_BOT_TOKEN, TG_CHAT_ID, GITHUB_STATE_TOKEN, GITHUB_STATE_REPO. Settings + edge history live on the
trishula-state branch (state/bb_config.json, state/bb_history.json), shared with what TRISHULA saved before.
"""
import builtins
import logging

import streamlit as st

from core import state as ST
from core.bbfeed import BBFeed
from core.timeutil import now_et
from core.version import BB_VERSION as VERSION
from tabs import spxbb as TAB

logging.getLogger("tastytrade").setLevel(logging.WARNING)

st.set_page_config(page_title=f"SPX BB v{VERSION}", page_icon="🔱", layout="wide")
st.markdown("""<style>
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"], [class*="viewerBadge"] {display:none !important;}
header[data-testid="stHeader"] {background: transparent;}
.block-container {padding-top: 1rem;}
div[data-testid="stMetricValue"] {font-size: 1.35rem;}
/* v0.45.0: input fields stand out from the panels */
[data-testid="stNumberInputContainer"], .stSelectbox .react-aria-ComboBox > div {
  background-color: #232c3b !important; border: 1px solid #4a5872 !important; border-radius: 6px !important;}
[data-testid="stNumberInputContainer"] *, .stSelectbox .react-aria-ComboBox > div * {background-color: transparent !important;}
[data-testid="stNumberInputContainer"] input, .stSelectbox input {color: #ffffff !important; font-weight: 600 !important;}
[data-testid="stNumberInputContainer"]:hover, .stSelectbox .react-aria-ComboBox > div:hover {border-color: #6b7d99 !important;}
[data-testid="stNumberInputContainer"]:focus-within {border-color: #1e90ff !important; box-shadow: 0 0 0 1px #1e90ff66;}
.st-key-bb_sc [data-testid="stNumberInputContainer"] {border-left: 6px solid #2f8bff !important;}
.st-key-bb_sp [data-testid="stNumberInputContainer"] {border-left: 6px solid #e040fb !important;}
.st-key-bb_sc label p, .st-key-bb_sp label p, .st-key-bb_aa label p {font-size: 1.0rem !important; color: #e6edf3 !important; font-weight: 600 !important;}
</style>""", unsafe_allow_html=True)

missing = [k for k in ("TT_CLIENT_SECRET", "TT_REFRESH_TOKEN") if k not in st.secrets]
if missing:
    st.error(f"Missing Streamlit secrets: {', '.join(missing)} — copy TRISHULA's secrets into this app's Settings → Secrets.")
    st.stop()

ST.configure(str(st.secrets.get("GITHUB_STATE_TOKEN", "") or ""),
             str(st.secrets.get("GITHUB_STATE_REPO", "") or "") or None)


@st.cache_resource(show_spinner=False)
def get_feed(version: str) -> BBFeed:
    """One feed per version; a newer upload stops the older one (kept in builtins across module reloads)."""
    old = getattr(builtins, "_spxbb_feed", None)
    if old is not None and getattr(old, "version", None) != version:
        old.stop()
    f = BBFeed(st.secrets["TT_CLIENT_SECRET"], st.secrets["TT_REFRESH_TOKEN"])
    f.version = version
    builtins._spxbb_feed = f
    return f.start()


@st.cache_resource(show_spinner=False)
def get_bb(version: str):
    """Tracker: 0.05-bid edges every 5 s + Telegram (TG_BOT_TOKEN / TG_CHAT_ID from secrets). One per version."""
    from core.bb import Tracker
    old = getattr(builtins, "_spxbb_tracker", None)
    if old is not None and getattr(old, "_version", None) != version:
        old.stop()
    t = Tracker(feed, st.secrets.get("TG_BOT_TOKEN", ""), st.secrets.get("TG_CHAT_ID", ""))
    t._version = version
    builtins._spxbb_tracker = t
    return t.start()


feed = get_feed(VERSION)
feed.start()                    # restarts the thread if it ever died
trk = get_bb(VERSION).start()   # the tracker + alerts run whether or not anyone is logged in


def _password_gate():
    """APP_PASSWORD from Streamlit secrets, same as TRISHULA. Feed and alerts keep running behind it."""
    import hmac
    pw = str(st.secrets.get("APP_PASSWORD", "") or "")
    if not pw or st.session_state.get("_auth_ok"):
        return
    st.markdown("### 🔱 SPX BB")
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


@st.fragment(run_every=30)
def status_bar():
    age = (now_et().timestamp() * 1000 - feed.last_event_ms) / 1000 if feed.last_event_ms else None
    dot = "🟢" if (age is not None and age < 120) else "🟡" if (age is not None and age < 600) else "🔴"
    err = f" · ⚠ {feed.errors[-1]['err'][:100]}" if feed.errors and "live" not in feed.state else ""
    st.caption(f"{dot} SPX BB v{VERSION} · feed: {feed.state} · last quote "
               f"{'—' if age is None else f'{age:.0f}s ago'}{err} · {now_et():%a %H:%M:%S} ET")


st.markdown(f"### 🔱 SPX BB <span style='font-size:0.7em;color:#8b949e'>v{VERSION}</span>", unsafe_allow_html=True)
status_bar()
TAB.render(trk)
