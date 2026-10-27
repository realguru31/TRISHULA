import numpy as np, pandas as pd, pickle, warnings, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt, matplotlib.dates as md
warnings.filterwarnings("ignore")
from scipy.stats import norm
src=open("dtgrid2.py").read()
exec(src.split("\nrows=[]")[0].replace("def run2(","def _unused(",1))      # D, pre, F, events, prep
def squares(x, mode):
    rth=x["rth"]; S=x["S"].values; nf,nfd,vol=prep[x["day"]]
    if mode=="yours": M,floor_c,prox,watch,alpha=nf,200,0.75,10,None
    else:             M,floor_c,prox,watch,alpha=nf,200,0.30,15,0.25
    K=M.columns.values.astype(float); cum=M.cumsum().values; dot=pre[x["day"]].reindex(K).fillna(0).values
    rv=vol.rolling(30,min_periods=5).sum().fillna(0).values; seen=np.zeros(len(K)); out=[]
    for i in range(len(rth)):
        d=np.abs(K-S[i]); w=np.where(d<=S[i]*prox/100)[0]; w=w[np.argsort(d[w])][:watch]
        band=np.maximum(np.abs(dot[w])*0.05,floor_c) if alpha is None else np.maximum(alpha*rv[i,w],floor_c)
        mv=cum[i,w]; n=np.floor(np.abs(mv)/band); new=np.maximum(n-seen[w],0); seen[w]=np.maximum(seen[w],n)
        for j,nn,m_ in zip(w,new,mv):
            if nn>0:
                dt_=dot[j]; filled=(abs(dt_)<floor_c) or (np.sign(dt_)==np.sign(m_))
                out.append((rth[i],K[j],1 if m_>0 else -1,filled))
    return pd.DataFrame(out,columns=["t","k","s","filled"])
def signals(x,H):
    rth=x["rth"]; g=F[F.day==x["day"]]
    sig=pd.Series(0.0,index=rth)
    for i,t in enumerate(rth):
        h=H[(H.t>t-pd.Timedelta("3min"))&(H.t<=t)]
        b=h[h.s>0].k.nunique(); m=h[h.s<0].k.nunique(); sig.iat[i]=(b if b>=1 else 0)-(m if m>=1 else 0)
    up=sig>=2; dn=sig<=-2
    fol=events(g,up.reindex(g.index).fillna(False),dn.reindex(g.index).fillna(False))
    ab=events(g,((sig<=-2)&(g.dp5>=-1)).reindex(g.index).fillna(False),((sig>=2)&(g.dp5<=1)).reindex(g.index).fillna(False))
    return fol,ab
days=["2026-10-08","2026-10-14","2026-10-16","2026-10-19"]
fig,axes=plt.subplots(4,2,figsize=(20,20),facecolor="#0b0f14")
for r,day in enumerate(days):
    x=[y for y in D if y["day"]==day][0]
    for c,mode in enumerate(("yours","v2")):
        ax=axes[r,c]; ax.set_facecolor("#0d1530"); H=squares(x,mode)
        for s,col in ((1,"#1e90ff"),(-1,"#ff00ff")):
            h=H[(H.s==s)&H.filled]; ax.scatter(h.t,h.k,s=10,marker="s",color=col,lw=0)
            h=H[(H.s==s)&~H.filled]; ax.scatter(h.t,h.k,s=10,marker="s",facecolors="none",edgecolors=col,lw=0.7)
        ax.plot(x["rth"],x["S"].values,color="white",lw=1.1)
        title=f"{day} · {'YOUR DT (band 5 % of dot, floor 200, ±0.75 %, 10)' if mode=='yours' else 'DT v2 (adaptive band 0.25×own 30-min vol, floor 200, ±0.3 %)'} · {len(H)/len(x['rth'])*60:.0f} squares/h"
        if mode=="v2":
            fol,ab=signals(x,H); g=F[F.day==day]
            for _,e in fol.iterrows():
                ok=e.r20>0; ax.scatter(e.t,g.S.loc[e.t]+(6 if e.d>0 else -6),marker="^" if e.d>0 else "v",s=110,
                                       color="#2ecc71" if ok else "#ff4d6d",edgecolors="white",lw=0.6,zorder=4)
            for _,e in ab.iterrows():
                ok=e.r20>0; ax.scatter(e.t,g.S.loc[e.t],marker="D",s=90,facecolors="none",edgecolors="#2ecc71" if ok else "#ff4d6d",lw=2,zorder=4)
            title+=f" · ▲▼ follow {len(fol)} ({(fol.r20>0).mean():.0%} right, {fol.r20.mean():+.1f} pts) · ◇ absorbed fade {len(ab)}"
        ax.set_title(title,color="#ddd",fontsize=9); ax.tick_params(colors="#9aa",labelsize=7); ax.xaxis.set_major_formatter(md.DateFormatter("%H:%M"))
        ax.set_ylim(x["S"].min()-45,x["S"].max()+45)
fig.text(0.5,0.005,"■ blue = bullish paper (calls bought / puts sold) · ■ magenta = bearish · filled = extending · hollow = unwinding · "
         "▲▼ v2 follow signal (≥2 net strikes within 3 min) · ◇ v2 absorbed → fade · green = right / red = wrong on the next 20 min",
         ha="center",color="#ddd",fontsize=11)
fig.tight_layout(rect=(0,0.015,1,1)); fig.savefig("dt_v2_pic.png",dpi=58,facecolor="#0b0f14")
