import numpy as np, pandas as pd
from scipy.stats import norm
D="/tmp/claude-0/-home-claude/dee3bb00-9e12-54e5-970a-89cb0441116b/scratchpad/oct16"
ET="America/New_York"
def et(ms): return pd.to_datetime(ms,unit="ms",utc=True).dt.tz_convert(ET).dt.tz_localize(None)
def load(bucket="10min"):
    c=pd.read_parquet(f"{D}/candles.parquet").drop_duplicates(["sym","ts_ms"],keep="last")
    c["base"]=c.sym.str.split("{").str[0]; c["t"]=et(c.ts_ms)
    legs=pd.read_parquet(f"{D}/legs.parquet").set_index("sym")
    o=c[c.base.str.startswith(".SPXW")].join(legs[["strike","cp"]],on="base")
    es=c[c.base.str.startswith("/ES")].set_index("t").sort_index()["close"]
    spx=c[c.base=="SPX"].set_index("t").sort_index()["close"]
    j=pd.concat([es.rename("es"),spx.rename("spx")],axis=1).dropna()
    basis=float((j.es-j.spx).median())
    spot=(es-basis); spot=spot.where(~spot.index.isin(spx.index), spx.reindex(spot.index))
    spot=pd.concat([spot, spx[~spx.index.isin(spot.index)]]).sort_index()
    o["bidv"]=o["bidv"].fillna(0); o["askv"]=o["askv"].fillna(0)
    o["b"]=o["t"].dt.floor(bucket)
    g=o.groupby(["b","strike","cp"]).agg(vol=("volume","sum"),buy=("askv","sum"),sell=("bidv","sum"),px=("close","last")).reset_index()
    sp=spot.groupby(spot.index.floor(bucket)).last()
    g["S"]=g["b"].map(sp)
    exp=pd.Timestamp("2026-10-16 16:00")
    g["T"]=np.maximum((exp-g["b"]).dt.total_seconds()/(365*24*3600), 1/(365*24*12))
    g["iv"]=implied_vol(g.px.values, g.S.values, g.strike.values, g["T"].values, g.cp.values)
    d1=(np.log(g.S/g.strike)+0.5*g.iv**2*g["T"])/(g.iv*np.sqrt(g["T"]))
    g["gamma"]=norm.pdf(d1)/(g.S*g.iv*np.sqrt(g["T"]))
    g["delta"]=np.where(g.cp==1, norm.cdf(d1), norm.cdf(d1)-1)
    return g, spot, basis

def bs(S,K,T,v,cp):
    d1=(np.log(S/K)+0.5*v*v*T)/(v*np.sqrt(T)); d2=d1-v*np.sqrt(T)
    return np.where(cp==1, S*norm.cdf(d1)-K*norm.cdf(d2), K*norm.cdf(-d2)-S*norm.cdf(-d1))
def implied_vol(px,S,K,T,cp):
    lo=np.full(len(px),0.01); hi=np.full(len(px),3.0)
    intr=np.where(cp==1, np.maximum(S-K,0), np.maximum(K-S,0))
    ok=np.isfinite(px)&np.isfinite(S)&(px>intr+0.01)
    for _ in range(60):
        mid=(lo+hi)/2; v=bs(S,K,T,mid,cp)
        hi=np.where(v>px,mid,hi); lo=np.where(v>px,lo,mid)
    out=(lo+hi)/2; out[~ok]=np.nan
    return out
if __name__=="__main__":
    g,spot,basis=load()
    print("basis",basis, g.shape, g.iv.describe().to_dict())
    print(spot.resample("1h").last().to_string())
