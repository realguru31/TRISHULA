"""Volume-spike filter for AG-REV ridges (one contract lighting up before the move —
the 7750C / 7645P reference shots), instead of every wiggle looking like a spike.

Per contract, per minute of volume v (contracts):
  1. OWN HISTORY  robust z = (log1p v − median) / (1.4826 · MAD) over the trailing
     `win` minutes of that contract only (current minute excluded); MAD floored so a
     contract that is usually silent does not divide by zero.
  2. CROSS-SECTION  v in the top `top_pct` of all recorded contracts that minute
     (a quiet far-OTM strike printing 20 lots cannot light up).
  3. SIZE FLOOR  v ≥ min_size contracts and premium ≥ min_prem.
A minute is a spike when 2 and 3 hold and (1 ≥ zthr, or — while the contract has no baseline yet,
e.g. the first 15 min after 09:30 — its cross-sectional robust z across the chain ≥ zthr + 1).
Baselines are separate for GTH (overnight, far thinner) and RTH, which restarts at 09:30:
for the first `min_hist` RTH minutes only rules 2 + 3 can fire.

Defaults tuned on real tastytrade tape (Fri 16 Oct RTH: 87.5k prints, 99.9th pct
contract-minute 1,501 lots; Sun-night GTH: 27.8k prints, median print 1 lot):
  RTH  z ≥ 4 · top 2 % · ≥ 200 contracts · ≥ $50k   → 15 spikes on Friday (all-legs z3/5%/50 gave 486)
  GTH  z ≥ 3 · top 5 % · ≥ 50 contracts · ≥ $25k    → 30 overnight (≈ 1 per 12 min)
Single-leg tape only by default (spreadLeg prints are packages). Legs of one unflagged
package (same minute, sizes within 2 %) are merged into one event.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

DEFAULTS = dict(win=60, min_hist=15, zthr=3.0, top_pct=5.0, min_size=50, min_prem=25_000.0)   # GTH
RTH_DEFAULTS = dict(zthr=4.0, top_pct=2.0, min_size=200, min_prem=50_000.0)
WARM_RATIO = 3.0            # RTH warm-up: share of chain vs overnight share
SINGLE_LEG = False          # L8: total volume by default (AG's 7675P bar = all legs); toggle in ⚡ spike filter


def minute_table(p: pd.DataFrame) -> pd.DataFrame:
    """Per (minute, contract): size, premium, net side (bought − sold contracts)."""
    if p is None or p.empty:
        return pd.DataFrame(columns=["m", "sym", "strike", "cp", "size", "prem", "net"])
    d = p.assign(m=p["ts"].dt.floor("1min"), prem=p["size"] * p["px"] * 100.0,
                 net=np.sign(p["aggr"]) * p["size"])
    return d.groupby(["m", "sym"], as_index=False).agg(strike=("strike", "first"), cp=("cp", "first"),
                                                       size=("size", "sum"), prem=("prem", "sum"), net=("net", "sum"))


def _robust_z(L: pd.DataFrame, win: int, min_hist: int) -> pd.DataFrame:
    base = L.shift(1)
    med = base.rolling(win, min_periods=min_hist).median()
    mad = (base - med).abs().rolling(win, min_periods=min_hist).median()
    return (L - med) / (1.4826 * np.maximum(mad, 0.25))


def detect(mt: pd.DataFrame, day: dt.date, cfg: dict | None = None):
    """Returns (spikes DataFrame, wide volume matrix minutes × sym)."""
    c = dict(DEFAULTS, **(cfg or {}))
    cols = ["m", "sym", "strike", "cp", "size", "prem", "net", "z", "side"]
    if mt is None or mt.empty:
        return pd.DataFrame(columns=cols + ["legs"]), pd.DataFrame()
    V = mt.pivot_table(index="m", columns="sym", values="size", aggfunc="sum").sort_index()
    idx = pd.date_range(V.index.min(), V.index.max(), freq="1min")
    V = V.reindex(idx).fillna(0.0)
    P = mt.pivot_table(index="m", columns="sym", values="prem", aggfunc="sum").reindex(index=idx, columns=V.columns).fillna(0.0)
    L = np.log1p(V)
    rth_open = dt.datetime.combine(day, dt.time(9, 30))
    rth = V.index >= rth_open
    Z = pd.DataFrame(np.nan, index=V.index, columns=V.columns)
    hit = pd.DataFrame(False, index=V.index, columns=V.columns)
    rc = {**c, **RTH_DEFAULTS, **(c.get("rth") or {})}
    for seg, sc in ((~rth, c), (rth, rc)):      # separate GTH / RTH baselines and thresholds
        if not seg.any():
            continue
        Vs, Ps = V.loc[seg], P.loc[seg]
        Zs = _robust_z(L.loc[seg], int(c["win"]), int(c["min_hist"]))
        Z.loc[seg] = Zs.values
        q = Vs.quantile(1.0 - float(sc["top_pct"]) / 100.0, axis=1)
        cross = Vs.ge(q, axis=0) & (Vs > 0)
        floor = (Vs >= float(sc["min_size"])) & (Ps >= float(sc["min_prem"]))
        # L15a: warm-up minutes (no own RTH history yet — the first min_hist minutes after 09:30) must take a
        # much bigger SHARE of the chain than the contract had overnight (share ratio ≥ WARM_RATIO), instead of
        # firing on size alone (that flooded the open with 100+ "spikes").
        own = Zs >= float(sc["zthr"])
        if seg is rth and (~rth).any():
            Vg = V.loc[~rth].tail(int(c["win"]) * 4)
            base_share = (Vg.sum() + 1.0) / (Vg.sum().sum() + len(Vg.columns))
            share = Vs.div(Vs.sum(axis=1).replace(0, np.nan), axis=0)
            warm = share.div(base_share, axis=1) >= WARM_RATIO
            own = own | (Zs.isna() & warm)
        else:
            own = own | Zs.isna()
        hit.loc[seg] = (cross & floor & own).values
    if not hit.values.any():
        return pd.DataFrame(columns=cols + ["legs"]), V
    st = hit.stack()
    st = st[st]
    rows = pd.DataFrame({"m": st.index.get_level_values(0), "sym": st.index.get_level_values(1)})
    meta = mt.drop_duplicates("sym").set_index("sym")[["strike", "cp"]]
    rows = rows.join(meta, on="sym")
    key = mt.set_index(["m", "sym"])
    j = key.reindex(pd.MultiIndex.from_frame(rows[["m", "sym"]]))
    rows["size"] = j["size"].values
    rows["prem"] = j["prem"].values
    rows["net"] = j["net"].values
    rows["z"] = [Z.at[m, s] for m, s in zip(rows["m"], rows["sym"])]
    rows["side"] = np.where(rows["net"] > 0, "BOUGHT", np.where(rows["net"] < 0, "SOLD", "MID"))
    rows = merge_packages(rows)
    return rows[cols + ["legs"]].sort_values("m").reset_index(drop=True), V


def merge_packages(rows: pd.DataFrame) -> pd.DataFrame:
    """Same minute, sizes within 2 % → one package event (largest-premium leg kept,
    the others listed in 'legs')."""
    if rows.empty:
        rows["legs"] = []
        return rows
    rows = rows.sort_values(["m", "size"], ascending=[True, False]).reset_index(drop=True)
    keep, legs = [], []
    used = set()
    for m, g in rows.groupby("m", sort=False):
        idx = list(g.index)
        for i in idx:
            if i in used:
                continue
            grp = [j for j in idx if j not in used and abs(rows.at[j, "size"] - rows.at[i, "size"]) <= 0.02 * rows.at[i, "size"]]
            used.update(grp)
            lead = max(grp, key=lambda j: rows.at[j, "prem"])
            keep.append(lead)
            legs.append(" + ".join(f"{rows.at[j, 'strike']:,.0f}{'C' if rows.at[j, 'cp'] == 1 else 'P'}" for j in grp)
                        if len(grp) > 1 else "")
    out = rows.loc[keep].copy()
    out["legs"] = legs
    return out
