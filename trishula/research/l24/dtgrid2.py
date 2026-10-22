import numpy as np, pandas as pd, pickle, itertools, warnings; warnings.filterwarnings("ignore")
from scipy.stats import norm
exec(open("dtgrid.py").read().split("F=pd.read_pickle")[0].split("def run(")[0])     # D, pre
F=pd.read_pickle("F.pkl"); exec(open("study.py").read().split("rows=[]")[0])
days=sorted(F.day.unique()); W1,W2=days[:6],days[6:]
prep={}
for x in D:
    rth=x["rth"]; o=x["o"]; S=x["S"]
    T=np.maximum((pd.Timestamp(f"{x['day']} 16:00")-o.t).dt.total_seconds().values/(365*86400),60/(365*86400))
    s_=S.reindex(o.t).values; d1=np.log(s_/o.strike.values)/(0.18*np.sqrt(T))+0.5*0.18*np.sqrt(T)
    ad=np.abs(np.where(o.cp.values==1,norm.cdf(d1),norm.cdf(d1)-1))
    o=o.assign(nf=np.where(o.cp==1,1.0,-1.0)*(o.askv-o.bidv)); o["nfd"]=o.nf*ad
    nf=o.pivot_table(index="t",columns="strike",values="nf",aggfunc="sum").reindex(rth).fillna(0)
    nfd=o.pivot_table(index="t",columns="strike",values="nfd",aggfunc="sum").reindex(rth).reindex(columns=nf.columns).fillna(0)
    vol=o.pivot_table(index="t",columns="strike",values="volume",aggfunc="sum").reindex(rth).reindex(columns=nf.columns).fillna(0)
    prep[x["day"]]=(nf,nfd,vol)
def run2(x, wmode, bmode, floor_c, alpha, prox, watch, clus):
    rth=x["rth"]; S=x["S"].values; nf,nfd,vol=prep[x["day"]]
    M=(nfd if wmode=="delta" else nf); K=M.columns.values.astype(float); cum=M.cumsum().values
    dot=pre[x["day"]].reindex(K).fillna(0).values
    if wmode=="delta": dot=dot*0.5
    rv=vol.rolling(30,min_periods=5).sum().fillna(0).values      # strike's own last-30-min volume
    seen=np.zeros(len(K)); last_k=np.full(len(K),-99); blue=np.zeros(len(rth)); mag=np.zeros(len(rth))
    hits=[]   # (i, strike_idx, sign)
    base=np.zeros(len(K))
    for i in range(len(rth)):
        d=np.abs(K-S[i]); w=np.where(d<=S[i]*prox/100)[0]; w=w[np.argsort(d[w])][:watch]
        if bmode=="dot": band=np.maximum(np.abs(dot[w])*0.05,floor_c)
        else: band=np.maximum(alpha*rv[i,w]*(0.5 if wmode=="delta" else 1.0),floor_c)
        mv=cum[i,w]+dot[w]-dot[w]          # move since the open (dot only sets the band)
        n=np.floor(np.abs(mv)/band); new=np.maximum(n-seen[w],0); seen[w]=np.maximum(seen[w],n)
        for j,nn in zip(w,new):
            if nn>0: hits.append((i,j,1 if cum[i,j]>0 else -1))
    H=pd.DataFrame(hits,columns=["i","j","s"])
    sig=np.zeros(len(rth))
    if len(H):
        for i in range(len(rth)):
            h=H[(H.i>i-3)&(H.i<=i)]
            b=h[h.s>0].j.nunique(); m=h[h.s<0].j.nunique()
            sig[i]=(b if b>=clus else 0)-(m if m>=clus else 0)
    return len(H), pd.Series(sig,index=rth)
rows=[]
grid=[(w,b,f,a,p,15,c) for w in ("contracts","delta") for b in ("dot","adaptive") for f in (100,200,400,800)
      for a in ((0.25,0.5,1.0) if b=="adaptive" else (0,)) for p in (0.3,0.75) for c in (1,2,3)]
print(len(grid),"settings",flush=True)
for gi,(wm,bm,fl,al,px,wt,cl) in enumerate(grid):
    nsq=0; parts=[]
    for x in D:
        n,s=run2(x,wm,bm,fl,al,px,wt,cl); nsq+=n; parts.append(s.rename("sig"))
    G=F.join(pd.concat(parts))
    sq_hr=nsq/len(F)*60
    for rn in ("plain follow","absorbed fade","confirmed follow"):
        for thr in (1,2,3):
            sg=G.sig
            if rn=="plain follow": u,d=sg>=thr,sg<=-thr
            elif rn=="absorbed fade": u,d=(sg<=-thr)&(G.dp5>=-1),(sg>=thr)&(G.dp5<=1)
            else: u,d=(sg>=thr)&(G.dp5>=3),(sg<=-thr)&(G.dp5<=-3)
            res={}
            for wn,wd in (("w1",W1),("w2",W2)):
                m=G.day.isin(wd); E=events(G[m],u[m],d[m]); res[wn]=(len(E),E.r20.mean() if len(E) else np.nan,(E.r20>0).mean() if len(E) else np.nan)
            rows.append(dict(weight=wm,band=bm,floor=fl,alpha=al,prox=px,agree=cl,thr=thr,rule=rn,sq_hr=sq_hr,
                             n1=res["w1"][0],r1=res["w1"][1],h1=res["w1"][2],n2=res["w2"][0],r2=res["w2"][1],h2=res["w2"][2]))
    if gi%20==0: print(gi,flush=True)
pd.DataFrame(rows).to_pickle("dtgrid2.pkl")
