import numpy as np, pandas as pd, warnings, itertools; warnings.filterwarnings("ignore")
exec(open("dtpic.py").read().split("def squares")[0])            # D, pre, F, events, prep
days_all=sorted(F.day.unique()); W1,W2=days_all[:6],days_all[6:]
def squares_cd(x, mode, cool):
    rth=x["rth"]; S=x["S"].values; nf,nfd,vol=prep[x["day"]]
    if mode=="yours": floor_c,prox,watch,alpha=200,0.75,10,None
    else: floor_c,prox,watch,alpha=200,0.30,15,0.25
    M=nf; K=M.columns.values.astype(float); cum=M.cumsum().values; dot=pre[x["day"]].reindex(K).fillna(0).values
    rv=vol.rolling(30,min_periods=5).sum().fillna(0).values; seen=np.zeros(len(K)); last=np.full(len(K),-999); out=[]
    for i in range(len(rth)):
        d=np.abs(K-S[i]); w=np.where(d<=S[i]*prox/100)[0]; w=w[np.argsort(d[w])][:watch]
        band=np.maximum(np.abs(dot[w])*0.05,floor_c) if alpha is None else np.maximum(alpha*rv[i,w],floor_c)
        mv=cum[i,w]; n=np.floor(np.abs(mv)/band); new=np.maximum(n-seen[w],0); seen[w]=np.maximum(seen[w],n)
        for j,nn,m_ in zip(w,new,mv):
            if nn>0 and i-last[j]>=cool: out.append((i,K[j],1 if m_>0 else -1)); last[j]=i
    return pd.DataFrame(out,columns=["i","k","s"])
def bursts(x,H,need):
    """one label per burst: net distinct strikes over 3 min ≥ need; label by price over the same 3–5 min."""
    rth=x["rth"]; S=x["S"].values; n=len(rth); sig=np.zeros(n)
    for i in range(n):
        h=H[(H.i>i-3)&(H.i<=i)]; sig[i]=h[h.s>0].k.nunique()-h[h.s<0].k.nunique()
    return pd.Series(sig,index=rth)
rows=[]
for mode in ("yours","v2"):
  for cool in (0,5,10,15,30):
    sigs=pd.concat([bursts(x,squares_cd(x,mode,cool),2) for x in D]).rename("sig"); G=F.join(sigs)
    nsq=None
    for thr in (1,2,3):
        dirn=np.sign(G.sig)*(np.abs(G.sig)>=thr)
        conf=(dirn*G.dp5>=3); absb=(dirn!=0)&(G.dp5.abs()<=1); rej=(dirn*G.dp5<=-3)
        labels={"plain follow":(dirn>0,dirn<0),
                "one label: confirmed→follow":((dirn>0)&conf,(dirn<0)&conf),
                "one label: absorbed→fade":((dirn<0)&absb,(dirn>0)&absb),
                "one label: rejected→fade":((dirn<0)&rej,(dirn>0)&rej),
                "one label: all three combined":(((dirn>0)&conf)|((dirn<0)&(absb|rej)),((dirn<0)&conf)|((dirn>0)&(absb|rej)))}
        for ln,(u,d) in labels.items():
            res={}
            for wn,wd in (("w1",W1),("w2",W2)):
                m=G.day.isin(wd); E=events(G[m],u[m],d[m])
                res[wn]=(len(E),E.r20.mean() if len(E) else np.nan,(E.r20>0).mean() if len(E) else np.nan,f"{(E.groupby('day').r20.mean()>0).sum()}/{E.day.nunique()}" if len(E) else "-")
            rows.append(dict(dt=mode,cooldown=cool,thr=thr,rule=ln,n1=res["w1"][0],r1=res["w1"][1],h1=res["w1"][2],d1=res["w1"][3],n2=res["w2"][0],r2=res["w2"][1],h2=res["w2"][2],d2=res["w2"][3]))
    print(mode,cool,flush=True)
R=pd.DataFrame(rows); R["both"]=(R.r1>0)&(R.r2>0)&(R.n1>=10)&(R.n2>=10); R["minr"]=R[["r1","r2"]].min(axis=1)
R.to_pickle("idea3.pkl")
print("\nshare positive both weeks by rule:"); print(R.groupby(["dt","rule"]).both.mean().unstack(0).round(2).to_string())
print("\nby cooldown:"); print(R.groupby(["dt","cooldown"]).both.mean().unstack(0).round(2).to_string())
print("\nTOP robust:"); print(R[R.both].sort_values("minr",ascending=False).head(15).round(2).to_string(index=False))
