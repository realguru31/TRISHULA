import numpy as np, pandas as pd, itertools, warnings; warnings.filterwarnings("ignore")
F=pd.read_pickle("F.pkl")
def events(F, up, dn, cool=10):
    out=[]
    for day,g in F.groupby("day"):
        u=up[g.index.isin(g.index)] if False else up.loc[g.index] if isinstance(up,pd.Series) else None
        last=-999
        uu=up[F.day==day].values; dd=dn[F.day==day].values; idx=g.index
        for i in range(len(g)):
            if i-last<cool: continue
            d=1 if uu[i] else (-1 if dd[i] else 0)
            if d and i>=10:
                out.append((day,idx[i],d,g.fw10.iat[i]*d,g.fw20.iat[i]*d,g.fw30.iat[i]*d)); last=i
    return pd.DataFrame(out,columns=["day","t","d","r10","r20","r30"])
def summ(E):
    if len(E)<15: return None
    byd=E.dropna(subset=["r20"]).groupby("day").r20.mean()
    return dict(n=len(E), r10=E.r10.mean(), r20=E.r20.mean(), r30=E.r30.mean(), hit20=(E.r20>0).mean(),
                days_pos=f"{(byd>0).sum()}/{len(byd)}", t20=E.r20.mean()/(E.r20.std()/np.sqrt(E.r20.notna().sum())+1e-9))
rows=[]
acts={"any":pd.Series(True,index=F.index)}
for z in (2,3,5): 
    for k in (3,5): acts[f"ztot{k}>={z}"]=F[f"ztot{k}"]>=z
for b in (3,5,8):
    for k in (3,5): acts[f"br{k}>={b}"]=F[f"br{k}"]>=b
for an,act in acts.items():
  for k in (3,5,10):
    sh=F[f"share{k}"]; dp=F[f"dp{k}"]
    for s in (0.05,0.1,0.15,0.2):
      for p in (0,1,2):
        up=act&(sh<=-s)&(dp>=-p); dn=act&(sh>=s)&(dp<=p)            # absorption → fade the flow
        r=summ(events(F,up,dn)); 
        if r: rows.append(dict(family="absorption (fade flow, price stalls)",act=an,k=k,s=s,p=p,**r))
      for P in (2,4,6):
        up=act&(sh>=s)&(dp>=P); dn=act&(sh<=-s)&(dp<=-P)             # initiation → follow
        r=summ(events(F,up,dn))
        if r: rows.append(dict(family="initiation (follow flow+price)",act=an,k=k,s=s,p=P,**r))
        r=summ(events(F,dn,up))
        if r: rows.append(dict(family="chase (fade flow+price)",act=an,k=k,s=s,p=P,**r))
      up=act&(sh<=-s); dn=act&(sh>=s)
      r=summ(events(F,up,dn))
      if r: rows.append(dict(family="flow contrarian",act=an,k=k,s=s,p=np.nan,**r))
  for X in (8,12,16,20):
      up=act&(F.dp15<=-X); dn=act&(F.dp15>=X)
      r=summ(events(F,up,dn))
      if r: rows.append(dict(family="exhaustion (fade 15-min move)",act=an,k=15,s=np.nan,p=X,**r))
      r=summ(events(F,dn,up))
      if r: rows.append(dict(family="momentum (follow 15-min move)",act=an,k=15,s=np.nan,p=X,**r))
  for k in (5,10):
    for n in (10,20,40):
      up=act&(F[f"dt{k}"]>=n); dn=act&(F[f"dt{k}"]<=-n)
      r=summ(events(F,up,dn))
      if r: rows.append(dict(family="DT follow",act=an,k=k,s=np.nan,p=n,**r))
      r=summ(events(F,dn,up))
      if r: rows.append(dict(family="DT fade",act=an,k=k,s=np.nan,p=n,**r))
R=pd.DataFrame(rows); R.to_pickle("R.pkl")
print(len(R),"configs")
# robust ranking: consistency across days + t-stat
R["dpos"]=R.days_pos.str.split("/").str[0].astype(int); R["dn"]=R.days_pos.str.split("/").str[1].astype(int)
R["cons"]=R.dpos/R.dn
print("== best per family (by t20, needing ≥30 events and ≥70% of days positive)")
G=R[(R.n>=30)&(R.cons>=0.7)].sort_values("t20",ascending=False)
print(G.groupby("family").head(2).round(2).to_string(index=False))
print("== family medians (all configs)")
print(R.groupby("family")[["r20","hit20","t20","cons"]].median().round(2).sort_values("t20",ascending=False).to_string())
