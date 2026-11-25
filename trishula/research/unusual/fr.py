import sys, json, numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/trishula/trishula")
X = "/tmp/claude-0/-home-claude/dee3bb00-9e12-54e5-970a-89cb0441116b/scratchpad/days/x/"
DAYS = {"2026-11-12": "trishula_day_20261112_close", "2026-11-16": "trishula_day_20261116_close",
        "2026-11-18": "trishula_day_20261118_close", "2026-11-20": "trishula_day_20261120_close",
        "2026-11-23": "trishula_day_20261123_1400", "2026-11-24": "d1124_1400full"}
def spx_frame(day, d):
    p = pd.read_parquet(X + d + "/prints.parquet", columns=["ts_ms","sym","exp","strike","cp","px","size","bid","ask","aggr","spread_leg","eth","valid","spot"])
    p = p[(p.exp.astype(str) == day) & p.valid.astype(bool)]
    c = pd.read_parquet(X + d + "/chain_snapshots.parquet", columns=["ts_ms","sym","oi"])
    oi = c.dropna(subset=["oi"]).sort_values("ts_ms").groupby("sym")["oi"].first()
    s = pd.read_parquet(X + d + "/spx1m.parquet"); mp = dict(zip((s.ts_ms // 60000) * 60000, s.close))
    S = p.spot.values.astype(float); miss = ~np.isfinite(S)
    S[miss] = pd.Series((p.ts_ms.values[miss] // 60000) * 60000).map(mp).values
    f = pd.DataFrame({"ts_ms": p.ts_ms.values.astype("int64"), "sym": p.sym.astype(str).values, "strike": p.strike.values.astype(float),
                      "cp": p.cp.values.astype(float), "px": p.px.values.astype(float), "size": p["size"].values.astype(float),
                      "bid": p.bid.values.astype(float), "ask": p.ask.values.astype(float), "aggr": np.nan_to_num(p.aggr.values.astype(float)),
                      "sl": ~p.spread_leg.fillna(False).values.astype(bool), "eth": p.eth.fillna(False).values.astype(bool), "S": S,
                      "oi": p.sym.astype(str).map(oi).values.astype(float)})
    return f.sort_values("ts_ms", kind="stable").reset_index(drop=True)
def x_frame(day, d, mkt):
    try: x = pd.read_parquet(X + d + f"/x_{mkt.lower()}_prints.parquet")
    except Exception: return pd.DataFrame()
    x = x[x.valid.astype(bool)]
    oi = (json.load(open(X + d + "/oi_log.json")) or {}).get(day, {})
    f = pd.DataFrame({"ts_ms": x.ts_ms.values.astype("int64"), "sym": x.sym.astype(str).values, "strike": x.strike.values.astype(float),
                      "cp": x.cp.values.astype(float), "px": x.px.values.astype(float), "size": x["size"].values.astype(float),
                      "bid": x.bid.values.astype(float), "ask": x.ask.values.astype(float), "aggr": np.nan_to_num(x.aggr.values.astype(float)),
                      "sl": ~x.spread_leg.values.astype(bool), "eth": x.eth.values.astype(bool), "S": x.und.values.astype(float),
                      "oi": x.sym.astype(str).map(lambda s: oi.get(s, np.nan)).values.astype(float)})
    return f.sort_values("ts_ms", kind="stable").reset_index(drop=True)
def xexp(day, d, mkt):
    st = json.load(open(X + d + "/status.json"))
    return ((st.get("xinfo") or {}).get(mkt) or {}).get("exp", "")
