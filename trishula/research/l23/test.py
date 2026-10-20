import numpy as np, pandas as pd, sys, warnings; warnings.filterwarnings("ignore")
from turns import *
out=[]
for day in ("20oct","16oct"):
    o,s,allm,t0,t1=load(day)
    vol=per_strike(o,allm,"volume"); ask=per_strike(o,allm,"askv"); bid=per_strike(o,allm,"bidv")
    cp=np.array([c for _,c in vol.columns]); K=np.array([k for k,_ in vol.columns])
    # bullish contracts per minute: calls bought + puts sold ; bearish: calls sold + puts bought
    bull=ask.loc[:,cp==1].sum(axis=1)*0; 
    bullm=np.where(cp[None,:]==1, ask.values, bid.values); bearm=np.where(cp[None,:]==1, bid.values, ask.values)
    def zsc(V,W,sm=1):
        V=pd.DataFrame(V,index=allm).rolling(sm,center=True,min_periods=1).mean() if sm>1 else pd.DataFrame(V,index=allm)
        b=V.shift(1); med=b.rolling(W,min_periods=10).median(); mad=(b-med).abs().rolling(W,min_periods=10).median()
        return ((V-med)/(1.4826*mad+1)).clip(lower=0)
    near=lambda: (np.abs(K[None,:]-s.values[:,None])<=50)      # strikes within ±50 of spot at each minute
    N=near()
    sig={}
    V=vol.values
    sig["B contracts (sum near spot)"]=pd.Series((V*N).sum(1),index=allm)
    sig["B contracts (max strike)"]=pd.Series((V*N).max(1),index=allm)
    for W,sm in ((30,1),(60,1),(60,3),(120,1)):
        Z=zsc(V,W,sm).values*N
        sig[f"E z{W}{' sm3' if sm>1 else ''} (max)"]=pd.Series(np.nanmax(Z,1),index=allm)
        sig[f"E z{W}{' sm3' if sm>1 else ''} (#>4)"]=pd.Series((Z>4).sum(1),index=allm)
    Zb=zsc(bullm,60).values*N; Zs=zsc(bearm,60).values*N
    sig["dir z60 bull−bear (sum)"]=pd.Series(np.nansum(Zb,1)-np.nansum(Zs,1),index=allm)
    netd=pd.Series(((bullm-bearm)*N).sum(1),index=allm)
    sig["net bull−bear contracts"]=netd
    rng=(allm>=t0)&(allm<=t1)
    for th in (8,12):
        piv=zigzag(s[rng],th); piv=piv[(piv.t>t0+pd.Timedelta("15min"))]
        for name,x in sig.items():
            xx=x[rng]; ab=xx.abs() if name.startswith(("dir","net")) else xx
            thr=ab.quantile(0.90)
            hot=ab>=thr
            # window around pivot: [-10,+2] min
            hits=[bool(hot[(hot.index>=p-pd.Timedelta("10min"))&(hot.index<=p+pd.Timedelta("2min"))].any()) for p in piv.t]
            # baseline: same window at every minute
            roll=hot.astype(int)[::-1].rolling(13,min_periods=1).max()[::-1].shift(-2).fillna(0)   # any hot in [t-10,t+2]
            base=hot.rolling(13,min_periods=1).max().shift(-2).fillna(0).mean()
            hr=np.mean(hits) if hits else np.nan
            dirok=np.nan
            if name.startswith(("dir","net")):
                ok=[]
                for p,k in zip(piv.t,piv.kind):
                    w=xx[(xx.index>=p-pd.Timedelta("10min"))&(xx.index<=p+pd.Timedelta("2min"))]
                    if len(w): ok.append((w.sum()<0) if k=="top" else (w.sum()>0))
                dirok=np.mean(ok) if ok else np.nan
            out.append((day,th,len(piv),name,hr,base,hr/base if base else np.nan,dirok))
r=pd.DataFrame(out,columns=["day","zz_pts","turns","signal","hit_rate","base_rate","lift","dir_right"])
r.to_pickle("turn_res.pkl")
print(r.round(2).to_string(index=False))
