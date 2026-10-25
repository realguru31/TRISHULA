import numpy as np, pandas as pd, warnings; warnings.filterwarnings("ignore")
exec(open("dtpic.py").read().split("days=[")[0])
days_all=sorted(F.day.unique()); W1,W2=days_all[:6],days_all[6:]
rows=[]
cache={}
for x in D:
    for mode in ("yours","v2"): cache[(x["day"],mode)]=squares(x,mode)
def sig_series(x,H,which):
    rth=x["rth"]; S=x["S"]
    if which=="off-pattern":
        sp=S.reindex(H.t).values; H=H[((H.s>0)&(H.k>sp))|((H.s<0)&(H.k<sp))]
    elif which=="on-pattern":
        sp=S.reindex(H.t).values; H=H[((H.s>0)&(H.k<=sp))|((H.s<0)&(H.k>=sp))]
    sig=pd.Series(0.0,index=rth)
    for i,t in enumerate(rth):
        h=H[(H.t>t-pd.Timedelta("3min"))&(H.t<=t)]
        sig.iat[i]=h[h.s>0].k.nunique()-h[h.s<0].k.nunique()
    return sig
for mode in ("yours","v2"):
  for which in ("all squares","off-pattern","on-pattern"):
    parts=[sig_series(x,cache[(x["day"],mode)],which) for x in D]
    G=F.join(pd.concat(parts).rename("sig"))
    for thr in (1,2,3):
      for rule in ("follow","confirmed follow (price ≥3 in 5 min)","fade"):
        if rule=="follow": u,d=G.sig>=thr,G.sig<=-thr
        elif rule.startswith("confirmed"): u,d=(G.sig>=thr)&(G.dp5>=3),(G.sig<=-thr)&(G.dp5<=-3)
        else: u,d=G.sig<=-thr,G.sig>=thr
        res={}
        for wn,wd in (("w1",W1),("w2",W2)):
            m=G.day.isin(wd); E=events(G[m],u[m],d[m]); res[wn]=(len(E),E.r20.mean() if len(E) else np.nan,(E.r20>0).mean() if len(E) else np.nan)
        rows.append(dict(dt=mode,squares=which,thr=thr,rule=rule,n1=res["w1"][0],r1=res["w1"][1],h1=res["w1"][2],n2=res["w2"][0],r2=res["w2"][1],h2=res["w2"][2]))
R=pd.DataFrame(rows); R["both"]=(R.r1>0)&(R.r2>0)&(R.n1>=10)&(R.n2>=10)
print(R.round(2).to_string(index=False)); R.to_pickle("offpat.pkl")
