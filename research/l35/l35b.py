import sys, itertools, pickle; B="/tmp/claude-0/-home-claude/dee3bb00-9e12-54e5-970a-89cb0441116b/scratchpad"
sys.path.insert(0,B+"/l28"); sys.path.insert(0,"/home/claude/trishula")
import numpy as np, pandas as pd, warnings; warnings.filterwarnings("ignore")
import l29
from core import dtv2 as V, signals as SG
def load():
    D=[x for x in l29.load_all() if x["day"]!="2026-10-21"]
    c=pd.read_parquet(B+"/d21full/candles.parquet"); c=c[c.ts_ms<2e12]
    ch=pd.read_parquet(B+"/d21full/chain.parquet"); xc=pd.read_parquet(B+"/d21full/xchain.parquet")
    S,rth=l29.spx(c,"2026-10-21")
    o=l29.opts(c,pd.concat([ch[["sym","exp","strike","cp"]],xc[xc.exp=="2026-10-22"][["sym","exp","strike","cp"]]]))
    D.append(dict(day="2026-10-21",S=S,rth=rth,o=o)); return sorted(D,key=lambda x:x["day"])
import os
MODE=os.environ.get("MODE","01")
def add_1dte(D):
    for x in D:
        if (x["o"]["exp"]!=x["day"]).any(): continue
        f=B+f"/oih/{x['day'].replace('-','')}"
        if not os.path.exists(f+"/candles.parquet"): continue
        c=pd.read_parquet(f+"/candles.parquet"); L=pd.read_parquet(f+"/legs.parquet")
        c=c[c.sym.str.contains("=m")&c.sym.str.startswith(".SPXW")].copy(); c["base"]=c.sym.str.split("{").str[0]
        L1=L[L.exp!=x["day"]]; c=c.merge(L1[["sym","exp","strike","cp"]],left_on="base",right_on="sym",suffixes=("_x",""))
        c["t"]=l29._t(c.ts_ms); c[["bidv","askv","volume"]]=c[["bidv","askv","volume"]].fillna(0)
        c=c[(c.t.dt.date==pd.Timestamp(x["day"]).date())]
        x["o"]=pd.concat([x["o"],c[["t","base","exp","strike","cp","volume","bidv","askv","close"]]],ignore_index=True)
    return D
D=add_1dte(load()); print(len(D),"days:",[x["day"] for x in D],"MODE",MODE,flush=True)
print("days with 1DTE:",sum((x["o"]["exp"]!=x["day"]).any() for x in D),flush=True)
GR={"S1":list(itertools.product([3,5,7,10,15,20,30],[0.8,0.9,0.95])),"S3":[(n,) for n in [300,500,750,1000,1500,2000,3000]],
    "S4":list(itertools.product([1,2,3,4],[0.15,0.25,0.5])),"S5":list(itertools.product([0.03,0.05,0.08,0.10,0.15],[3,4,6])),
    "S6":list(itertools.product([6,8,10,12,16],[3,5,7])),"S7":list(itertools.product([500,1000,2000],[5,10],[10,15,25]))}
def blocks(o,S,rth,k,share,mode,rng_max=None):
    sig=pd.Series(0,index=rth); oo=o
    big=(oo.volume>=np.maximum(100 if mode=="S1" else k, (k if mode=="S1" else share)*oo.med.fillna(np.inf)))
    if mode=="S1": side=0.0+share
    else: side=0.9
    bought=oo.askv>=side*oo.volume; sold=oo.bidv>=side*oo.volume
    d=np.where(bought,np.where(oo.cp==1,1,-1),np.where(sold,np.where(oo.cp==1,-1,1),0)); m=(big&(d!=0)).values
    e=oo[m].assign(d=d[m])
    if mode=="S1": ref=S.diff(15)
    else: ref=S.rolling(30,min_periods=20).max()-S.rolling(30,min_periods=20).min()
    for t,g in e.groupby("t"):
        dd=int(np.sign(g.d.sum()))
        if not dd or t not in ref.index or ref[t]!=ref[t]: continue
        if mode=="S1" and np.sign(ref[t])==-dd: sig[t]=dd
        if mode=="S7" and ref[t]<=rng_max: sig[t]=dd
    return SG.cool(sig)
def s6(nf,vol,S,rth,pts,br):
    s=pd.Series(0,index=rth)
    K=vol.columns.values.astype(float); Sv=S.reindex(vol.index).ffill().values; N=np.abs(K[None,:]-Sv[:,None])<=50
    b=vol.shift(1); med=b.rolling(30,min_periods=10).median(); mad=(b-med).abs().rolling(30,min_periods=10).median()
    Z=((vol-med)/(1.4826*mad+1)).values; brs=pd.Series(((Z>4)&N).sum(1),index=vol.index).rolling(5,min_periods=1).max()
    dp=S.diff(15); s=pd.Series(np.where((brs>=br)&(dp>=pts),-1,np.where((brs>=br)&(dp<=-pts),1,0)),index=rth)
    s[s.index<rth[0]+pd.Timedelta(minutes=10)]=0; return SG.cool(s)
EV=[]
for x in D:
    S,rth,o=x["S"],x["rth"],x["o"]; o=o[(o.t>=rth[0])&(o.t<=rth[-1])].sort_values("t").copy()
    o["med"]=o.groupby("base").volume.transform(lambda v: v.where(v>0).expanding().median().shift(1))
    o0=o[o.exp==x["day"]]
    oa=o if MODE=="01" else o0                    # flow used by EVERY signal in this mode
    ob=o0 if MODE=="0" else o
    nf,vol=SG.frames(oa,rth)
    fw=S.shift(-20)-S; valid=fw.dropna().index; mu=float(fw.loc[valid].mean())
    def add(code,p,sg):
        for t,d in sg[sg!=0].items():
            if t in valid: EV.append((x["day"],code,p,t,int(d),float(fw[t]*d),float(fw[t]*d-mu*d)))
    for p in GR["S1"]: add("S1",p,blocks(ob,S,rth,p[0],p[1],"S1"))
    for p in GR["S7"]: add("S7",p,blocks(ob,S,rth,p[0],p[1],"S7",p[2]))
    for p in GR["S3"]: add("S3",p,SG.s3_flip(oa,S,rth,p[0]))
    for p in GR["S4"]: add("S4",p,V.follow(V.squares(nf,vol,S,alpha=p[1]),rth,need=p[0]))
    for p in GR["S5"]: add("S5",p,V.initiation(nf,vol,S,share=p[0],pts=p[1]))
    for p in GR["S6"]: add("S6",p,s6(nf,vol,S,rth,p[0],p[1]))
    print(x["day"],"done",len(EV),flush=True)
E=pd.DataFrame(EV,columns=["day","code","p","t","d","r20","edge"]); E.to_pickle(f"l35_events_{MODE}.pkl")
