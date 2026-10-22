import numpy as np, pandas as pd, pickle, glob, itertools, warnings, sys; warnings.filterwarnings("ignore")
B="/tmp/claude-0/-home-claude/dee3bb00-9e12-54e5-970a-89cb0441116b/scratchpad"
_t=lambda ms: pd.to_datetime(ms,unit="ms",utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
D=pickle.load(open("days.pkl","rb"))
src={x["day"]:None for x in D}
for d in glob.glob(f"{B}/md/2026*"): src[f"{d[-8:-4]}-{d[-4:-2]}-{d[-2:]}"]=(f"{d}/candles.parquet",pd.read_parquet(f"{d}/legs.parquet"))
src["2026-10-16"]=(f"{B}/oct16/candles.parquet",pd.read_parquet(f"{B}/oct16/legs.parquet"))
src["2026-10-20"]=(f"{B}/today/candles.parquet",pd.read_parquet(f"{B}/today/chain.parquet"))
pre={}
for x in D:
    p,legs=src[x["day"]]; c=pd.read_parquet(p); c=c[c.sym.str.startswith(".SPXW")&(c.ts_ms<2e12)].copy()
    c["base"]=c.sym.str.split("{").str[0]; c=c.merge(legs[["sym","strike","cp"]],left_on="base",right_on="sym",suffixes=("_x",""))
    c["t"]=_t(c.ts_ms); c=c[c.t<x["rth"][0]]
    for col in ("bidv","askv"): c[col]=c[col].fillna(0)
    c["nf"]=np.where(c.cp==1,1.0,-1.0)*(c.askv-c.bidv)
    pre[x["day"]]=c.groupby("strike").nf.sum()            # overnight participant book = the "dot"
def run(x, band_pct, floor_c, prox, watch):
    rth=x["rth"]; S=x["S"].values; o=x["o"]
    nf=o.assign(nf=np.where(o.cp==1,1.0,-1.0)*(o.askv-o.bidv)).pivot_table(index="t",columns="strike",values="nf",aggfunc="sum").reindex(rth).fillna(0)
    K=nf.columns.values.astype(float); cum=nf.cumsum().values
    dot=pre[x["day"]].reindex(K).fillna(0).values
    band=np.maximum(np.abs(dot)*band_pct/100,floor_c)
    seen=np.zeros(len(K)); blue=np.zeros(len(rth)); mag=np.zeros(len(rth))
    for i in range(len(rth)):
        d=np.abs(K-S[i]); w=np.where(d<=S[i]*prox/100)[0]; w=w[np.argsort(d[w])][:watch]
        mv=cum[i,w]; n=np.floor(np.abs(mv)/band[w])
        new=np.maximum(n-seen[w],0); seen[w]=np.maximum(seen[w],n)
        blue[i]=new[mv>0].sum(); mag[i]=new[mv<0].sum()
    return pd.DataFrame({"blue":blue,"mag":mag},index=rth)
F=pd.read_pickle("F.pkl")
exec(open("study.py").read().split("rows=[]")[0])
days=sorted(F.day.unique()); W1,W2=days[:6],days[6:]
grid=list(itertools.product((3,5,10,15),(100,200,400,800),(0.3,0.5,0.75,1.0),(6,10,14)))
rows=[]
for gi,(bp,fl,px,wt) in enumerate(grid):
    parts=[]
    for x in D:
        r=run(x,bp,fl,px,wt); r["day"]=x["day"]; parts.append(r)
    R=pd.concat(parts); G=F.join(R[["blue","mag"]])
    sq_per_hr=(G.blue+G.mag).groupby(G.day).sum().mean()/6.5
    net5=(G.blue-G.mag).groupby(G.day).transform(lambda s:s.rolling(5,min_periods=1).sum())
    net10=(G.blue-G.mag).groupby(G.day).transform(lambda s:s.rolling(10,min_periods=1).sum())
    for q in (0.80,0.90,0.95):                       # signal threshold = top (1-q) of |net| for this config
        t5=max(net5.abs().quantile(q),1); t10=max(net10.abs().quantile(q),1)
        rules={"plain follow":(net5>=t5,net5<=-t5),
               "confirmed follow":((net10>=t10)&(G.dp10>=6),(net10<=-t10)&(G.dp10<=-6)),
               "absorbed fade":((net5<=-t5)&(G.dp5>=-1),(net5>=t5)&(G.dp5<=1))}
        for rn,(u,d) in rules.items():
            res={}
            for wn,wd in (("w1",W1),("w2",W2)):
                m=G.day.isin(wd); E=events(G[m],u[m],d[m]); res[wn]=(len(E),E.r20.mean() if len(E) else np.nan,(E.r20>0).mean() if len(E) else np.nan)
            rows.append(dict(band=bp,floor=fl,prox=px,watch=wt,q=q,rule=rn,sq_hr=sq_per_hr,
                             n1=res["w1"][0],r1=res["w1"][1],h1=res["w1"][2],n2=res["w2"][0],r2=res["w2"][1],h2=res["w2"][2]))
    if gi%24==0: print(gi,len(grid),flush=True)
pd.DataFrame(rows).to_pickle("dtgrid.pkl")
