import numpy as np, pandas as pd, warnings; warnings.filterwarnings("ignore")
from scipy.stats import spearmanr
P=pd.read_pickle("P_rth.pkl"); ks=list(P.index)
o=pd.read_pickle("../l21/opt.pkl"); s=pd.read_pickle("../l21/spot.pkl")
o=o[o.strike.isin(ks)].copy()
from scipy.stats import norm
S=s.reindex(o.t,method="ffill").values; T=np.maximum((pd.Timestamp("2026-10-20 16:00")-o.t).dt.total_seconds().values/(365*86400),300/(365*86400))
iv=o.imp_vol.fillna(0.2).values; d1=(np.log(S/o.strike.values)+0.5*iv*iv*T)/(iv*np.sqrt(T))
o["adelta"]=np.abs(np.where(o.cp.values==1,norm.cdf(d1),norm.cdf(d1)-1))
o["prem"]=o.volume*o.close*100; o["dnot"]=o.volume*o.adelta*100*S; o["net"]=(o.askv-o.bidv).abs()
allm=pd.date_range("2026-10-19 20:15","2026-10-20 10:36",freq="1min")
def mat(col, comb):
    x=o.pivot_table(index="t",columns=["strike","cp"],values=col,aggfunc="sum").reindex(allm).fillna(0)
    c=x.xs(1,axis=1,level=1).reindex(columns=ks).fillna(0); p=x.xs(-1,axis=1,level=1).reindex(columns=ks).fillna(0)
    return {"sum":c+p,"max":np.maximum(c,p),"call":c,"put":p}[comb]
def trans(V, tr):
    if tr=="raw": return V
    if tr=="sqrt": return np.sqrt(V)
    if tr=="log": return np.log1p(V)
    if tr.startswith("ratio"):
        W=int(tr[5:]); med=V.shift(1).rolling(W,min_periods=5).median(); return V/(med+1)
    if tr.startswith("z"):
        W=int(tr[1:]); b=V.shift(1); med=b.rolling(W,min_periods=5).median(); mad=(b-med).abs().rolling(W,min_periods=5).median()
        return ((V-med)/(1.4826*mad+1)).clip(lower=0)
    if tr.startswith("lz"):
        W=int(tr[2:]); L=np.log1p(V); b=L.shift(1); mu=b.rolling(W,min_periods=5).mean(); sd=b.rolling(W,min_periods=5).std()
        return ((L-mu)/(sd+0.3)).clip(lower=0)
    if tr=="share": return V.div(V.sum(axis=1)+1,axis=0)
    if tr=="xz": return V.sub(V.mean(axis=1),axis=0).div(V.std(axis=1)+1e-9,axis=0)
    if tr=="strike_peak": return V/(V.max()+1e-9)
def peakify(V): return (V-V.rolling(15,center=True,min_periods=3).median()).clip(lower=0)
rows=[]
Pv=P.values; Pr=P.columns
for col in ("volume","prem","dnot","net"):
  for comb in ("sum","max","call","put"):
    V0=mat(col,comb)
    for sm in (1,3):
      V1=V0.rolling(sm,center=True,min_periods=1).mean() if sm>1 else V0
      for tr in ("raw","sqrt","log","ratio15","ratio30","ratio60","ratio120","z15","z30","z60","z120","lz30","lz60","lz120","share","xz","strike_peak"):
        X=trans(V1,tr).reindex(Pr)
        for pk in (False,True):
          Y=peakify(X) if pk else X
          a=Y.values.T; m=np.isfinite(a)
          g=spearmanr(a[m],Pv[m]).correlation
          per=[spearmanr(a[i][m[i]],Pv[i][m[i]]).correlation for i in range(len(ks)) if np.std(Pv[i])>0 and np.std(a[i][m[i]])>0]
          # top-peak hit rate: of AG's top 40 cells, how many are in candidate's top 15%
          thr=np.nanquantile(a,0.85); top=np.argsort(Pv.ravel())[-40:]
          hit=np.mean(a.ravel()[top]>=thr)
          rows.append((g,np.nanmean(per),hit,col,comb,sm,tr,pk))
r=pd.DataFrame(rows,columns=["glob","per_strike","top40_hit","metric","side","smooth","transform","peakified"])
r["score"]=r.glob+r.per_strike+0.5*r.top40_hit
r.to_pickle("ridge_res.pkl")
print(len(r)); print(r.sort_values("score",ascending=False).head(25).round(3).to_string(index=False))
print("--- current v0.16.2 (premium raw, sum, smooth3, global):"); print(r[(r.metric=="prem")&(r.side=="sum")&(r.smooth==3)&(r.transform=="raw")].round(3).to_string(index=False))
