import sys; sys.path.insert(0,sys.argv[1]); from common import *
import datetime as dt
from core import dtv2 as V, signals as SG, spikes as SP
from core import expiry as EX
ET='America/New_York'
def et(ms): return pd.to_datetime(ms,unit='ms',utc=True).dt.tz_convert(ET).dt.tz_localize(None)
zips=ZIPS
lean={d['day']:d for d in days()}
allc=[]; base=[]
for day,z in zips.items():
    Z=f"{S}/data/{z}/"; dday=pd.Timestamp(day).date(); e1=None
    legs={k:tuple(v) for k,v in json.load(open(Z+'legs.json')).items()}
    exps=sorted({v[0] for v in legs.values() if v[0]>=day}); e1=exps[1] if len(exps)>1 else None
    b=LN.bars(lean[day],'0DTE','single-leg',1)
    o_=pd.Timestamp(day)+pd.Timedelta('9h30min'); last=b.index[-1]
    rth=pd.date_range(o_,last,freq='1min'); spot=b.c.reindex(rth).ffill()
    p=pd.read_parquet(Z+'prints.parquet',columns=['ts_ms','sym','exp','strike','cp','ev_type','px','size','aggr','spread_leg'])
    p=p[(p.exp.astype(str).isin([day]+([e1] if e1 else []))) & (p.ev_type.astype(str)!='2')]
    p['ts']=et(p.ts_ms); p=p[(p.ts>=o_)&(p.ts<=last+pd.Timedelta('59s'))]
    c1=pd.read_parquet(Z+'opt1m_backfill.parquet'); c1=c1[(c1.m>=o_)&(c1.m<=last)]
    c5=pd.read_parquet(Z+'candles5.parquet')
    # ---- DT v2 (0DTE, tested defaults, dot=None)
    p0=p[p.exp.astype(str)==day]; c10=c1[c1.sym.map(lambda s:(legs.get(s) or ('',))[0])==day]
    # fill5
    first=p0.groupby('sym').ts_ms.min(); q=c5[c5.sym.map(lambda s:(legs.get(s) or ('',))[0])==day]; q=q[q.vol>0]
    q=q[q.ts_ms+300000<=q.sym.map(first).fillna(np.inf)]
    rows=[pd.DataFrame({'ts_ms':q.ts_ms.values+k*60000,'sym':q.sym.values,'size':q.vol.values/5,'net':(q.askv-q.bidv).values/5}) for k in range(5)]
    f5=pd.concat(rows); f5['m']=et(f5.ts_ms); f5=f5[(f5.m>=o_)&(f5.m<=last)]
    f5=f5[~pd.MultiIndex.from_arrays([f5.m,f5.sym]).isin(pd.MultiIndex.from_arrays([c10.m,c10.sym]))]
    f5['strike']=f5.sym.map(lambda x:legs[x][1]); f5['cp']=f5.sym.map(lambda x:legs[x][2]); f5['prem']=0.0
    cc=pd.concat([c10[["m","sym","strike","cp","size","prem","net"]],f5[["m","sym","strike","cp","size","prem","net"]]],ignore_index=True)
    mt=SP.minute_table(p0)
    have=pd.MultiIndex.from_arrays([cc.m,cc.sym]); keep=mt[~pd.MultiIndex.from_arrays([mt.m,mt.sym]).isin(have)]
    mt=pd.concat([cc,keep[cc.columns]],ignore_index=True); mt=mt[(mt.m>=o_)&(mt.m<=last)]
    nf,vol=V.minute_frames(mt,rth)
    sq=V.squares(nf,vol,spot,None); fo=V.follow(sq,rth); ini=V.initiation(nf,vol,spot)
    ch=pd.read_parquet(Z+'chain_snapshots.parquet'); ch=ch[ch.exp.astype(str)==day]
    gex=pd.Series(dtype=float)
    if len(ch):
        t0=ch.ts_ms.min(); g=ch[ch.ts_ms==t0]; g=ch.sort_values('ts_ms').groupby('sym').first().reset_index()
        near=(g.strike-spot.iloc[0]).abs()<=25; iv=float(np.nanmedian(g.iv[near])) if near.any() else .16
        gex=V.gex_path(g[['strike','cp','oi']],spot,EX.end(dday),float(np.clip(iv,.05,1)))
    card=V.scorecard({'follow':fo,'initiation':ini},spot,gex).assign(day=day,src='DTv2')
    allc.append(card)
    # ---- Signals S1,S3-S7 all positions, 0DTE mode
    c1s=c1[c1.sym.isin(legs)]
    pm=p.assign(t=p.ts.dt.floor('1min'),base=p.sym.astype(str),volume=p['size'].astype(float),bidv=np.where(p.aggr<0,p['size'],0.0),askv=np.where(p.aggr>0,p['size'],0.0))
    pm=pm.groupby(['t','base'],as_index=False).agg(strike=('strike','first'),cp=('cp','first'),volume=('volume','sum'),bidv=('bidv','sum'),askv=('askv','sum'))
    o=SG.minute_flow(c1s,pm,legs)
    wf=SG.wf_table('0DTE')
    for pos in SG.POSITIONS:
        ev=SG.compute_picks(o,spot,rth,dday,SG.picks_for(pos,wf),'0DTE')
        sc=SG.score(ev,spot)
        if len(sc): allc.append(pd.DataFrame({'t':sc.t,'type':sc.code+'/'+pos,'dir':sc.d,'px':sc.px,'fw10':sc.fw10,'fw20':sc.fw20,'fw30':sc.fw30,'day':day,'src':'SIG','d':sc.d}))
    # baseline: every minute, long, fw h
    for h in (10,20,30):
        r=(spot.shift(-h)-spot).dropna()
        base.append(dict(day=day,h=h,long_mean=r.mean(),abs_mean=r.abs().mean(),n=len(r)))
    print(day,'rth min',len(rth),'squares',len(sq),'follow',int((fo!=0).sum()),'init',int((ini!=0).sum()),'gex>0 share',round(float((gex>0).mean()),2) if len(gex) else None, flush=True)
C=pd.concat(allc,ignore_index=True)
C['d']=C['d'].fillna(C['dir'].map(lambda x: 1 if (x==1 or str(x).startswith('▲')) else -1))
C.to_pickle(S+'/work/dt_card.pkl'); pd.DataFrame(base).to_pickle(S+'/work/base.pkl')
