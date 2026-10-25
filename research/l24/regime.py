import numpy as np, pandas as pd, warnings; warnings.filterwarnings("ignore")
src=open("offpat.py").read()
exec(src.split("\nfor mode in")[0])
rows=[]
for mode in ("yours","v2"):
    G=F.join(pd.concat([sig_series(x,cache[(x["day"],mode)],"all squares") for x in D]).rename("sig"))
    for L in (30,60,90):
        tr=G.groupby("day").S.transform(lambda s: s-s.shift(L))
        rngL=G.groupby("day").S.transform(lambda s: s.rolling(L,min_periods=10).max()-s.rolling(L,min_periods=10).min())
        eff=(tr.abs()/(rngL+1e-9))                         # efficiency: 1 = straight-line trend, 0 = chop
        for e in (0.5,0.6,0.7):
          for thr in (1,2):
            trending=eff>=e
            dirn=np.sign(G.sig)*(np.abs(G.sig)>=thr)
            # trending: follow DT only when it agrees with the trend; ranging: fade DT
            up=((trending)&(dirn>0)&(tr>0))|((~trending)&(dirn<0))
            dn=((trending)&(dirn<0)&(tr<0))|((~trending)&(dirn>0))
            res={}
            for wn,wd in (("w1",W1),("w2",W2)):
                m=G.day.isin(wd); E=events(G[m],up[m],dn[m]); res[wn]=(len(E),E.r20.mean() if len(E) else np.nan,(E.r20>0).mean() if len(E) else np.nan,
                                                                      f"{(E.groupby('day').r20.mean()>0).sum()}/{E.day.nunique()}")
            rows.append(dict(dt=mode,lookback=L,eff=e,thr=thr,n1=res["w1"][0],r1=res["w1"][1],h1=res["w1"][2],d1=res["w1"][3],
                             n2=res["w2"][0],r2=res["w2"][1],h2=res["w2"][2],d2=res["w2"][3]))
R=pd.DataFrame(rows); R["both"]=(R.r1>0)&(R.r2>0)
print(R.round(2).to_string(index=False)); print("\nshare positive both weeks:", R.groupby("dt").both.mean().round(2).to_dict())
R.to_pickle("regime.pkl")
