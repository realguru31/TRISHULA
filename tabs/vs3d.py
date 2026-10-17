"""VS3D — sub-tab bar for the vs3dgbt 0.9.79 port (engine pending APPROVE)."""
import streamlit as st

SUBTABS = ["VS3D (combined)", "Book (by strike)", "Terrain (gradient)", "Interval (bubbles)",
           "Market Read", "GEX³ (3-lens)", "DT"]


def render(rec):
    tabs = st.tabs(SUBTABS)
    s = rec.status()
    for t, name in zip(tabs, SUBTABS):
        with t:
            st.info(f"**{name}** — port of vs3dgbt 0.9.79 queued. The recorder is already "
                    f"collecting the data it needs ({s['chain_rows']:,} chain rows, "
                    f"{s['prints']:,} prints so far).")
