import numpy as np, pandas as pd, glob, os
B="/tmp/claude-0/-home-claude/dee3bb00-9e12-54e5-970a-89cb0441116b/scratchpad"
def _t(ms): return pd.to_datetime(ms,unit="ms",utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
def load_day(path_candles, legs_df, day):
    c=pd.read_parquet(path_candles); c=c[c.ts_ms<2e12]
    spx=c[c.sym.str.startswith("SPX{")].drop_duplicates("ts_ms").copy(); spx["t"]=_t(spx.ts_ms)
    spx=spx.set_index("t").sort_index()
    rth=pd.date_range(f"{day} 09:30",f"{day} 15:59",freq="1min")
    S=spx["close"].reindex(rth).ffill(); H=spx["high"].reindex(rth).ffill(); L=spx["low"].reindex(rth).ffill()
    o=c[c.sym.str.startswith(".SPXW")].copy(); o["base"]=o.sym.str.split("{").str[0]; o["t"]=_t(o.ts_ms)
    o=o.merge(legs_df[["sym","strike","cp"]],left_on="base",right_on="sym",suffixes=("_x",""))
    o=o[(o.t>=rth[0])&(o.t<=rth[-1])]
    for col in ("bidv","askv"): o[col]=o[col].fillna(0)
    return dict(day=day,S=S,H=H,L=L,o=o[["t","base","strike","cp","volume","bidv","askv","close"]],rth=rth)
def all_days():
    out=[]
    for d in sorted(glob.glob(f"{B}/md/2026*")):
        day=f"{d[-8:-4]}-{d[-4:-2]}-{d[-2:]}"
        out.append(load_day(f"{d}/candles.parquet", pd.read_parquet(f"{d}/legs.parquet"), day))
    out.append(load_day(f"{B}/oct16/candles.parquet", pd.read_parquet(f"{B}/oct16/legs.parquet"), "2026-10-16"))
    ch=pd.read_parquet(f"{B}/today/chain.parquet")
    out.append(load_day(f"{B}/today/candles.parquet", ch, "2026-10-20"))
    out=sorted(out,key=lambda x:x["day"])
    for x in out:   # trim 20 Oct to its data end
        last=x["o"].t.max(); x["rth"]=x["rth"][x["rth"]<=last]; x["S"]=x["S"].reindex(x["rth"]); x["H"]=x["H"].reindex(x["rth"]); x["L"]=x["L"].reindex(x["rth"])
    return out
