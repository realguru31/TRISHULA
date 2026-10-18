"""Common control bar shared by every tab: expiry + visible strike window."""
from __future__ import annotations

from datetime import date

import streamlit as st


def _label(e: str, i: int, types: dict) -> str:
    d = date.fromisoformat(e)
    t = types.get(e, "")
    tag = "M" if t in ("Regular", "Quarterly") else ("EOM" if t == "End-Of-Month" else "W")
    return f"{d:%a %d %b} · {i}DTE · {tag}" if i < 2 else f"{d:%a %d %b %Y} · {tag}"


def control_bar(rec) -> dict:
    exps = rec.all_exps or [str(e) for e in rec.exps]
    types = rec.exp_types
    c1, c2, c3, c4 = st.columns([1.3, 1.7, 1.0, 1.6])
    if not exps:
        c1.selectbox("Expiry", ["loading…"], disabled=True, key="cb_dis")
        return {"exp": None, "mode": "Strikes", "n": 20, "pct": 2.0}

    weekly_fri = next((e for e in exps if date.fromisoformat(e).weekday() == 4), exps[0])
    monthly = next((e for e in exps if types.get(e) in ("Regular", "Quarterly")), exps[-1])
    quick = {"0DTE": exps[0], "1DTE": exps[1] if len(exps) > 1 else exps[0],
             "Weekly": weekly_fri, "Monthly": monthly, "Other": None}
    pick = c1.segmented_control("Expiry", list(quick), default="0DTE", key="cb_quick")
    pick = pick or "0DTE"
    if pick == "Other":
        exp = c2.selectbox("Any listed expiry", exps[:60], key="cb_other",
                           format_func=lambda e: _label(e, exps.index(e), types))
    else:
        exp = quick[pick]
        c2.markdown(f"<div style='padding-top:1.9rem;color:#8b949e'>{_label(exp, exps.index(exp), types)}"
                    f"{'' if exp in rec._subscribed else ' · loading…'}</div>", unsafe_allow_html=True)
    mode = c3.segmented_control("Range", ["Strikes", "% move"], default="Strikes", key="cb_mode") or "Strikes"
    if mode == "Strikes":
        n = c4.slider("Strikes each side of spot", 5, 60, 20, key="cb_n")
        pct = 2.0
    else:
        pct = c4.slider("% move each side of spot", 0.5, 4.0, 2.0, 0.25, key="cb_pct")
        n = 20
    rec.request_expiry(exp)
    return {"exp": exp, "mode": mode, "n": n, "pct": pct}
