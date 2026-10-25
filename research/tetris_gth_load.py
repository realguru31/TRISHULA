import sys; sys.path.insert(0,"/home/claude/trishula")
import numpy as np, pandas as pd
from core.classify import bucket, aggr
G="/tmp/claude-0/-home-claude/dee3bb00-9e12-54e5-970a-89cb0441116b/scratchpad/gth"
ET="America/New_York"
def et(ms): return pd.to_datetime(ms,unit="ms",utc=True).dt.tz_convert(ET).dt.tz_localize(None)
def load():
    p=pd.read_parquet(f"{G}/prints.parquet"); c=pd.read_parquet(f"{G}/candles.parquet"); ch=pd.read_parquet(f"{G}/chain.parquet")
    p=p[(p["flags"].astype(int)&2)==0].copy()
    p["ts"]=et(p.ts_ms)
    b=[bucket(px,bi,a) for px,bi,a in zip(p.px,p.bid,p.ask)]
    p["aggr"]=[aggr(bb,px,bi,a,1.0,s) for bb,px,bi,a,s in zip(b,p.px,p.bid,p.ask,p.aggr_side.astype(str))]
    c=c.drop_duplicates(["sym","ts_ms"],keep="last")
    c["base"]=c.sym.str.split("{").str[0]; c["t"]=et(c.ts_ms)
    oc=c[c.base.str.startswith(".SPXW")].copy()
    meta=ch.set_index("sym")[["strike","cp"]]
    oc=oc.join(meta, on="base")
    es=c[c.base.str.startswith("/ES")].sort_values("t")
    # synthetic SPX per minute: median over strikes of C - P + K (1m option candle closes)
    w=oc.pivot_table(index=["t","strike"],columns="cp",values="close").dropna()
    syn=(w[1]-w[-1]+w.index.get_level_values(1)).groupby(level=0).median()
    syn=syn.rolling(5,min_periods=1).median()
    esm=es.set_index("t")["close"]
    basis=(esm.reindex(syn.index)-syn).dropna().median()
    spot=(esm-basis).rename("c").reset_index()
    return p,oc,ch,spot,basis
if __name__=="__main__":
    p,oc,ch,spot,basis=load()
    print("basis",basis, spot.c.describe()[["min","max"]].to_dict(), "last", spot.c.iloc[-1])
    x=oc[oc.base.str.contains("P7675")].set_index("t")["close"]; print("7675P close", x.min(), x.idxmin(), x.max(), x.iloc[-1])
