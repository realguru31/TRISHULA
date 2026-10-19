"""Volume-spike filter for AG-REV ridges (one contract lighting up before the move —
the 7750C / 7645P reference shots), instead of every wiggle looking like a spike.

Per contract, per minute of volume v (contracts):
  1. OWN HISTORY  robust z = (log1p v − median) / (1.4826 · MAD) over the trailing
     `win` minutes of that contract only (current minute excluded); MAD floored so a
     contract that is usually silent does not divide by zero.
  2. CROSS-SECTION  v in the top `top_pct` of all recorded contracts that minute
     (a quiet far-OTM strike printing 20 lots cannot light up).
  3. SIZE FLOOR  v ≥ min_size contracts and premium ≥ min_prem.
A minute is a spike when 2 and 3 hold and (1 ≥ zthr, or the contract has no baseline yet).
Baselines are separate for GTH (overnight, far thinner) and RTH, which restarts at 09:30:
for the first `min_hist` RTH minutes only rules 2 + 3 can fire.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

DEFAULTS = dict(win=60, min_hist=15, zthr=3.0, top_pct=5.0, min_size=50, min_prem=25_000.0)


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
        return pd.DataFrame(columns=cols), pd.DataFrame()
    V = mt.pivot_table(index="m", columns="sym", values="size", aggfunc="sum").sort_index()
    idx = pd.date_range(V.index.min(), V.index.max(), freq="1min")
    V = V.reindex(idx).fillna(0.0)
    P = mt.pivot_table(index="m", columns="sym", values="prem", aggfunc="sum").reindex(index=idx, columns=V.columns).fillna(0.0)
    L = np.log1p(V)
    rth_open = dt.datetime.combine(day, dt.time(9, 30))
    rth = V.index >= rth_open
    Z = pd.DataFrame(np.nan, index=V.index, columns=V.columns)
    for seg in (~rth, rth):                      # separate GTH / RTH baselines
        if seg.any():
            Z.loc[seg] = _robust_z(L.loc[seg], int(c["win"]), int(c["min_hist"])).values
    q = V.quantile(1.0 - float(c["top_pct"]) / 100.0, axis=1)
    cross = V.ge(q, axis=0) & (V > 0)
    floor = (V >= float(c["min_size"])) & (P >= float(c["min_prem"]))
    own = (Z >= float(c["zthr"])) | Z.isna()
    hit = cross & floor & own
    if not hit.values.any():
        return pd.DataFrame(columns=cols), V
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
    return rows[cols].sort_values("m").reset_index(drop=True), V
