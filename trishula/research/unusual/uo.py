import pandas as pd, numpy as np
ET = "America/New_York"; X = "/tmp/claude-0/-home-claude/dee3bb00-9e12-54e5-970a-89cb0441116b/scratchpad/days/x/"
DAYS = {"2026-11-12": "trishula_day_20261112_close", "2026-11-16": "trishula_day_20261116_close",
        "2026-11-18": "trishula_day_20261118_close", "2026-11-20": "trishula_day_20261120_close",
        "2026-11-23": "trishula_day_20261123_1400", "2026-11-24": "d1124_1400full"}
out = {}
for day, d in DAYS.items():
    p = pd.read_parquet(X + d + "/prints.parquet", columns=["ts_ms","sym","exp","cp","strike","aggr_side","size","px","bid","ask","delta","spot","spread_leg","cond"])
    p = p[(p.exp.astype(str) == day) & (~p.spread_leg.fillna(False).astype(bool)) & p.aggr_side.isin(["BUY","SELL"])]
    t = pd.to_datetime(p.ts_ms, unit="ms", utc=True).dt.tz_convert(ET)
    m = t.dt.hour * 60 + t.dt.minute
    p = p[(m >= 570) & (m < 960)].copy(); p["m"] = m[p.index]
    p["paid"] = np.where(p.aggr_side == "BUY", p.px >= p.ask, p.px <= p.bid)
    p["auct"] = p.cond.astype(str).str.contains("a", regex=False)
    p["sec"] = p.ts_ms // 1000
    o = p.groupby(["sym","aggr_side","sec"]).agg(ts=("ts_ms","first"), m=("m","first"), cp=("cp","first"), K=("strike","first"),
        size=("size","sum"), d=("delta", lambda x: np.nanmean(np.abs(x)) if x.notna().any() else np.nan), S=("spot","first"),
        paid=("paid","max"), auct=("auct","max")).reset_index()
    o["d"] = o["d"].fillna(0.3)
    o["dn"] = o.d * o["size"] * 100 * o.S
    o["dir"] = np.where((o.aggr_side == "BUY") == (o.cp > 0), 1, -1)
    o["b"] = ((o.m - 570) // 30).clip(0, 12)
    s = pd.read_parquet(X + d + "/spx1m.parquet").sort_values("ts_ms")
    st = pd.to_datetime(s.ts_ms, unit="ms", utc=True).dt.tz_convert(ET)
    s = s[st.dt.strftime("%Y-%m-%d") == day]; sm = (st[s.index].dt.hour * 60 + st[s.index].dt.minute).values
    px = pd.Series(s.close.values, index=sm).groupby(level=0).last().reindex(range(570, 961)).ffill()
    for h in (10, 20, 30):
        o[f"f{h}"] = (px.reindex(o.m + h).values - px.reindex(o.m).values) * o.dir
    out[day] = o
    print(day, len(o), flush=True)
pd.to_pickle(out, "uo_orders.pkl")
