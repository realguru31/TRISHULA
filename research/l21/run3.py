import numpy as np, pandas as pd, time, sys, warnings; warnings.filterwarnings("ignore")
from brute import fields, agg, norms2, pricegrid
from score2 import scores
tag=sys.argv[1]; Tp=sys.argv[2]; spotp=sys.argv[3]; optp=sys.argv[4]; chainp=sys.argv[5]; expc=sys.argv[6]
T=pd.read_pickle(Tp); s=pd.read_pickle(spotp)
chain=pd.read_parquet(chainp) if chainp.endswith("parquet") else pd.read_pickle(chainp); opt=pd.read_pickle(optp)
ks=list(T.index.astype(float)); K=np.array(ks)
F=fields(T.columns, ks, opt, chain, s, pd.Timestamp(expc))
St=s.reindex(T.columns,method="nearest").values
mask=np.isfinite(T.values) & (np.abs(K[:,None]-St[None,:])>7)
res=[]; t0=time.time()
for kind in ("strike","pricegrid"):
  for w in ("oi","cum","oicum","net","cumrth"):
    for g in ("gamma","vega","delta","one","vanna","charm"):
      if kind=="pricegrid" and g=="one": continue
      for comb in ("sum","cminusp","call","put"):
        M=agg(F,w,g,comb,ks) if kind=="strike" else pricegrid(F,w,g,comb,ks)
        for nn,MM in norms2(M):
          res.append(scores(MM,T,mask,K,St)+(kind,w,g,comb,nn))
          if kind=="pricegrid" and nn in ("none","d_open"):   # signed fields: also try |x|
              res.append(scores(np.abs(MM),T,mask,K,St)+(kind,w,g,comb,nn+"|abs"))
res=pd.DataFrame(res,columns=["glob","temporal","xsec","kind","weight","greek","comb","norm"])
res["combo"]=res.glob.fillna(0)+res.temporal.fillna(0)
res.to_pickle(f"res3_{tag}.pkl"); print(len(res), round(time.time()-t0,1),"s")
print("TOP temporal"); print(res.sort_values("temporal",ascending=False).head(15).round(3).to_string(index=False))
print("TOP combo"); print(res.sort_values("combo",ascending=False).head(12).round(3).to_string(index=False))
