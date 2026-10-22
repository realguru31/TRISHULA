import numpy as np, pandas as pd, warnings; warnings.filterwarnings("ignore")
from turns import *
import sys; sys.path.insert(0,"/home/claude/trishula")
from core.interval import dt_detect
rows=[]; evlog={}
for day in ("20oct","16oct"):
    o,s,allm,t0,t1=load(day)
    o=o.copy(); o["nf"]=np.where(o.cp==1,1.0,-1.0)*(o.askv-o.bidv)       # participant net paper: calls +, puts −; bought +, sold −
    per=o.pivot_table(index="t",columns="strike",values="nf",aggfunc="sum").reindex(allm).fillna(0)
    cum=per.cumsum()
    rth0=pd.Timestamp(f"{t0.date()} 09:30")
    for band_pct,floor_c,prox,watch in ((5,200,0.75,10),(5,100,0.75,10),(10,200,0.5,8),(3,100,1.0,14)):
        dot=cum.loc[:rth0].iloc[-1]                   # book at the open (overnight net)
        seen={}; ev=[]
        for m in cum.loc[t0:t1].index:
            sp=s.asof(m); w=sp*prox/100
            ks=sorted([k for k in cum.columns if abs(k-sp)<=w],key=lambda k:abs(k-sp))[:watch]
            for k in ks:
                d=float(dot.get(k,0)) if m>=rth0 else 0.0
                base=cum.loc[rth0,k] if m>=rth0 else 0.0
                cur=d+float(cum.loc[m,k])-base if m>=rth0 else float(cum.loc[m,k])
                key=(k, m>=rth0)
                n,g,b=dt_detect(d,cur,band_pct,floor_c,seen.get(key,0)); seen[key]=b
                if n and g: ev.append((m,k,g[0],g[1],n))
        E=pd.DataFrame(ev,columns=["t","k","c","f","n"])
        evlog[(day,band_pct,floor_c)]=E
        ts=pd.Series(0.0,index=cum.loc[t0:t1].index)
        bull=E[E.c=="blue"].groupby("t").n.sum().reindex(ts.index).fillna(0); bear=E[E.c=="magenta"].groupby("t").n.sum().reindex(ts.index).fillna(0)
        rec=E[E.f=="hollow"].groupby("t").n.sum().reindex(ts.index).fillna(0)
        tot=bull+bear
        for th in (8,12):
            piv=zigzag(s[t0:t1],th); piv=piv[piv.t>t0+pd.Timedelta("15min")]
            for name,x in (("DT all squares",tot),("DT receding (hollow)",rec),("DT bull−bear",bull-bear)):
                ab=x.abs(); thr=max(ab.quantile(0.90),1e-9); hot=ab>=thr
                win=lambda p: (hot.index>=p-pd.Timedelta("10min"))&(hot.index<=p+pd.Timedelta("2min"))
                hits=[bool(hot[win(p)].any()) for p in piv.t]
                base=hot.rolling(13,min_periods=1).max().shift(-2).fillna(0).mean()
                dirr=np.nan
                if name=="DT bull−bear":
                    ok=[(x[win(p)].sum()<0) if k=="top" else (x[win(p)].sum()>0) for p,k in zip(piv.t,piv.kind) if x[win(p)].abs().sum()>0]
                    dirr=np.mean(ok) if ok else np.nan
                rows.append((day,th,len(piv),f"{name} [{band_pct}%/{floor_c}/{prox}%/{watch}]",np.mean(hits),base,np.mean(hits)/base if base else np.nan,dirr,len(E)))
r=pd.DataFrame(rows,columns=["day","zz","turns","signal","hit","base","lift","dir_right","events"])
pd.to_pickle(evlog,"dt_events.pkl"); r.to_pickle("dt_res.pkl")
print(r.round(2).to_string(index=False))
