import sys, pickle, glob; sys.path.insert(0,"/home/claude/trishula")
import numpy as np, pandas as pd, datetime as dt
from core import tetris as TT
B="/tmp/claude-0/-home-claude/dee3bb00-9e12-54e5-970a-89cb0441116b/scratchpad/"
rng=np.random.default_rng(11)
_t=lambda ms: pd.to_datetime(ms,unit="ms",utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
def legs_from_syms(syms, day):
    tag=pd.Timestamp(day).strftime("%y%m%d"); out=[]
    for s in syms:
        if not s.startswith(f".SPXW{tag}"): continue
        rest=s[len(f".SPXW{tag}"):]; cp=1 if rest[0]=="C" else -1; out.append((s,float(rest[1:]),cp))
    return pd.DataFrame(out,columns=["sym","strike","cp"])
days=[]
for x in pickle.load(open(B+"md/days.pkl","rb")):
    d=x["day"]; f=B+f"oih/{d.replace('-','')}"
    sm=pd.read_parquet(f+"/summary.parquet"); c=pd.read_parquet(f+"/candles.parquet")
    dd=c[c.sym.str.contains("=d")].copy(); dd["base"]=dd.sym.str.split("{").str[0]; dd["t"]=_t(dd.ts_ms)
    dd=dd[dd.t.dt.date<pd.Timestamp(d).date()].sort_values("t").groupby("base").last()
    L=legs_from_syms(sorted(set(sm.sym.tolist())|set(dd.index.tolist())),d)
    oi_s=dict(zip(sm.sym,sm.oi)); L["oi"]=[oi_s.get(s_, dd["oi"].get(s_, np.nan)) if oi_s.get(s_)==oi_s.get(s_) else dd["oi"].get(s_, np.nan) for s_ in L.sym]
    L["iv"]=L.sym.map(dd["iv"])
    L["iv"]=pd.to_numeric(L.iv,errors="coerce"); L["iv"]=L.iv.where(L.iv>0,L.iv.median())
    days.append(dict(day=d,S=x["S"],L=L))
# 21 Oct
ch=pd.read_parquet(B+"d21full/chain.parquet"); c=pd.read_parquet(B+"d21full/candles.parquet"); c=c[c.ts_ms<2e12]
s=c[c.sym.str.startswith("SPX{")].drop_duplicates("ts_ms"); S=pd.Series(s.close.values,index=_t(s.ts_ms).values).sort_index()
rth=pd.date_range("2026-10-21 09:30","2026-10-21 15:59",freq="1min"); S=S.reindex(rth).ffill()
L=ch[ch.exp=="2026-10-21"][["sym","strike","cp","oi","iv"]].copy(); L["iv"]=pd.to_numeric(L.iv,errors="coerce"); L["iv"]=L.iv.where(L.iv>0,L.iv.median())
days.append(dict(day="2026-10-21",S=S,L=L))
def tetris(L,S,day,model):
    idx=pd.date_range(f"{day} 09:30",f"{day} 15:50",freq=TT.BUCKET)
    Sb=S.groupby(S.index.floor(TT.BUCKET)).last().reindex(idx).ffill().bfill()
    s0=float(Sb.iloc[0]); LL=L[(L.strike-s0).abs()<=200]
    M=TT.greek_field(LL,Sb,pd.Timestamp(f"{day} 16:00"),model)
    V=TT.per_strike_peak(M,0.0); Bd=TT.bands(V,"AG")
    ks=V.index.values.astype(float); keep=np.abs(ks-s0)<=100
    return pd.DataFrame(Bd[keep],index=ks[keep],columns=idx), Sb
rows=[]
for x in days:
    S=x["S"].dropna(); day=x["day"]
    fw={h:S.shift(-h)-S for h in (10,20,30)}; valid=fw[20].dropna().index
    for model in ("A","E"):
        Bd,Sb=tetris(x["L"],S,day,model)
        ks=Bd.index.values; prev_warm=None; last=None
        for j,t in enumerate(Bd.columns):
            te=t+pd.Timedelta(minutes=10)            # end of bucket = when the block is known
            if te not in S.index: continue
            k=ks[np.argmin(np.abs(ks-S[te]))]; warm=Bd.loc[k,t]>=4
            if prev_warm is not None and warm and not prev_warm and te>=pd.Timestamp(f"{day} 10:00"):
                mv=S[te]-S.get(te-pd.Timedelta(minutes=30),np.nan)
                if mv==mv and abs(mv)>=3 and (last is None or te-last>=pd.Timedelta(minutes=30)) and te in valid:
                    d=-int(np.sign(mv)); last=te
                    rnd=rng.choice(valid,200)
                    rows.append(dict(day=day,model=model,t=te,d=d,r10=fw[10].get(te,np.nan)*d,r20=fw[20][te]*d,r30=fw[30].get(te,np.nan)*d,
                                     ctrl=np.nanmean(fw[20].reindex(rnd).values)*d))
            prev_warm=warm
R=pd.DataFrame(rows); R["edge"]=R.r20-R.ctrl; R.to_pickle("l34_events.pkl")
for m,g in R.groupby("model"):
    t=g.edge.mean()/(g.edge.std()/np.sqrt(len(g))+1e-9); dpos=(g.groupby("day").edge.mean()>0).mean()
    print(f"model {m}: n {len(g)} on {g.day.nunique()} days · right {100*(g.r20>0).mean():.0f}% · avg20 {g.r20.mean():+.2f} · edge {g.edge.mean():+.2f} · t {t:.2f} · days positive {100*dpos:.0f}% · fw10 {g.r10.mean():+.2f} fw30 {g.r30.mean():+.2f}")
