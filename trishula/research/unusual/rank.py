import pandas as pd, numpy as np, heapq, sys
ET="America/New_York"
def orders(d, day):
    p = pd.read_parquet(d + "/prints.parquet", columns=["ts_ms","sym","exp","aggr_side","size","delta","spot","spread_leg"])
    p = p[(p.exp.astype(str) == day) & (~p.spread_leg.fillna(False).astype(bool))]
    p["t"] = pd.to_datetime(p.ts_ms, unit="ms", utc=True).dt.tz_convert(ET)
    p = p[(p.t.dt.time >= pd.Timestamp("09:30").time()) & (p.t.dt.time < pd.Timestamp("16:00").time())]
    p["sec"] = p.ts_ms // 1000
    o = p.groupby(["sym", "aggr_side", "sec"]).agg(ts=("ts_ms","first"), size=("size","sum"), d=("delta", lambda x: np.nanmean(np.abs(x))), S=("spot","first")).reset_index()
    o["dn"] = o["d"].fillna(0.3) * o["size"] * 100 * o["S"]
    o = o.sort_values("ts").reset_index(drop=True)
    o["hr"] = pd.to_datetime(o.ts, unit="ms", utc=True).dt.tz_convert(ET).dt.hour
    return o
days = {"11-16":"trishula_day_20261116_close","11-18":"trishula_day_20261118_close","11-23":"trishula_day_20261123_1400","11-24":"d1124_1400full"}
O = {k: orders(v, "2026-" + k) for k, v in days.items()}
N = 10
for k, o in O.items():
    h = []; run = np.zeros(len(o), bool)
    for i, v in enumerate(o.dn.values):
        if len(h) < N: heapq.heappush(h, v); run[i] = True
        elif v > h[0]: heapq.heapreplace(h, v); run[i] = True
    hind = np.zeros(len(o), bool); hind[o.dn.nlargest(N).index] = True
    print(k, len(o), "orders | running top-10 flags", run.sum(), "by hour", o[run].groupby("hr").size().to_dict(), "| hindsight by hour", o[hind].groupby("hr").size().to_dict())
pd.to_pickle(O, "/tmp/claude-0/-home-claude/dee3bb00-9e12-54e5-970a-89cb0441116b/scratchpad/mm/orders.pkl")
