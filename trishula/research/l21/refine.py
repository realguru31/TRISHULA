import numpy as np, pandas as pd, warnings; warnings.filterwarnings("ignore")
from scipy.stats import norm
from brute import fields
from score2 import scores
D="/tmp/claude-0/-home-claude/dee3bb00-9e12-54e5-970a-89cb0441116b/scratchpad/today"
T=pd.read_pickle("T_today.pkl"); s=pd.read_pickle("spot.pkl"); opt=pd.read_pickle("opt.pkl"); chain=pd.read_parquet(f"{D}/chain.parquet")
ks=list(T.index.astype(float)); K=np.array(ks)
F=fields(T.columns, ks, opt, chain, s, pd.Timestamp("2026-10-20 16:00"))
St=s.reindex(T.columns,method="nearest").values
mask=np.isfinite(T.values)&(np.abs(K[:,None]-St[None,:])>7)
def grid(fn, w, sgn):
    P=K; out=np.zeros((len(P),len(St)))
    for j in range(len(St)):
        T_=F["Tt"][j]; iv=F["IV"][j]; iv=np.where(iv>0,iv,0.2)
        PP=P[:,None]; KK=F["K"][None,:]; sq=np.sqrt(T_)
        d1=(np.log(PP/KK)+0.5*iv*iv*T_)/(iv*sq); d2=d1-iv*sq; pdf=norm.pdf(d1)
        g=dict(vanna=-pdf*d2/iv, avanna=np.abs(pdf*d2/iv), gamma=pdf/(PP*iv*sq), vega=PP*pdf*sq,
               vanna_c=-pdf*d2/iv*PP)[fn]
        out[:,j]=(g*(w[j]*sgn)[None,:]).sum(axis=1)
    return out
cp=F["cp"]; one=np.ones_like(cp,float); dsg=np.where(cp==1,1.,-1.)
rows=[]
for fn in ("vanna","avanna","gamma","vega","vanna_c"):
  for wn in ("oi","oicum","cum"):
    w=F["W"][wn]
    for sn,sg in (("sum",one),("dealer C+P-",dsg),("dealer C-P+",-dsg)):
      M=grid(fn,w,sg)
      for tr,X in (("raw",M),("abs",np.abs(M)),("neg",-M),("time_peak",np.abs(M)/np.abs(M).max(axis=0,keepdims=True))):
        rows.append(scores(X,T,mask,K,St)+(fn,wn,sn,tr))
r=pd.DataFrame(rows,columns=["glob","temporal","xsec","greek","weight","sign","xf"]); r["combo"]=r.glob+r.temporal
print(r.sort_values("combo",ascending=False).head(20).round(3).to_string(index=False))
r.to_pickle("refine_today.pkl")
