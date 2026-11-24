import sys; sys.path.insert(0,sys.argv[1]); from common import *
from core import extremes as XT, unusual as UN
from core.orderflow import implied_delta
ET='America/New_York'
ds=days()
# ---------- (c1) extremes, all lean days, walk-forward verdict
evs=[]
for d in ds:
    e=XT.events(d)
    if len(e): evs.append(e.assign(day=d['day']))
EV=pd.concat(evs,ignore_index=True)
import builtins; _p=print
print('EXTREMES all events:')
for k in ('fade','follow'):
    for ss in (False,True):
        e=EV[(EV.kind==k)&EV.pts.notna()]
        if ss: e=e[e.sess_ok]
        print(f"  {k:6s} sess={ss!s:5s}: n {len(e):3d}  right {(e.pts>0).mean():.0%}  avg30 {e.pts.mean():+.2f}  days+ {(e.groupby('day').pts.sum()>0).sum()}/{e.day.nunique()}")
print('  today:'); print(EV[EV.day==ds[-1]['day']][['t','side','kind','lean','dir','pts','sess_ok']].to_string(index=False))
wf=[]
for ss in (False,True):
    for d in ds:
        day=d['day']; hist=EV[EV.day<day]; sc=XT.score(hist,sess=ss); v=sc['verdict']
        tod=EV[(EV.day==day)&EV.pts.notna()]
        if ss: tod=tod[tod.sess_ok]
        tr=tod[tod.kind==v.lower()] if v!='SIT OUT' else tod.iloc[:0]
        wf.append(dict(sess=ss,day=day,verdict=v,n=len(tr),pts=tr.pts.sum()))
W=pd.DataFrame(wf); print('  walk-forward verdict per day:'); print(W.pivot(index='day',columns='sess',values=['verdict','n','pts']).to_string())
print('  WF totals:',W.groupby('sess')[['n','pts']].sum().to_dict())
# ---------- (c2) unusual + ES/SPY
zips={'2026-11-12':'z_20261112_close','2026-11-16':'z_20261116_close','2026-11-18':'z_20261118_close','2026-11-20':'z_20261120_close','2026-11-23':'z_20261123_1400','2026-11-24':'z_20261124_close'}
lean={d['day']:d for d in ds}
FL=[]; XC=[]; base={}
for day,z in zips.items():
    Z=f"{S}/data/{z}/"
    b=LN.bars(lean[day],'0DTE','single-leg',1); spot=b.c; idx=spot.index
    r30=(spot.shift(-30)-spot); base[day]=r30.mean()
    oi=json.load(open(Z+'oi_log.json')); prev=sorted(k for k in oi if k<day); oim=oi[prev[-1]] if prev else oi.get(day,{})
    p=pd.read_parquet(Z+'prints.parquet',columns=['ts_ms','sym','exp','strike','cp','ev_type','px','size','bid','ask','aggr','spread_leg','eth','valid','spot'])
    p=p[(p.exp.astype(str)==day)&(p.ev_type.astype(str)!='2')&p.valid.astype(bool)]
    sm=pd.Series(spot.values,index=idx.tz_localize(ET).as_unit("ms").asi8); S_=p.spot.values.astype(float)
    miss=~np.isfinite(S_); S_[miss]=pd.Series((p.ts_ms.values[miss]//60000)*60000).map(sm).values
    f=pd.DataFrame({'ts_ms':p.ts_ms.values.astype('int64'),'sym':p.sym.values,'strike':p.strike.values.astype(float),'cp':p.cp.values.astype(float),'px':p.px.values.astype(float),'size':p['size'].values.astype(float),'bid':p.bid.values.astype(float),'ask':p.ask.values.astype(float),'aggr':np.nan_to_num(p.aggr.values.astype(float)),'sl':~p.spread_leg.values.astype(bool),'eth':p.eth.values.astype(bool),'S':S_,'oi':p.sym.astype(str).map(oim).values.astype(float)})
    f=f.sort_values('ts_ms',kind='stable').reset_index(drop=True)
    prm=dict(UN.DEF,drop_mid=True,drop_cross=True)
    o,bu=UN.detect(f,'SPX',pd.Timestamp(day),'single-leg',['big','burst','pay','new'],prm,exp=day)
    for k in ('big','burst','pay','new'):
        q=o[o[k]]
        for r in q.itertuples():
            t=pd.Timestamp(r.ts_ms,unit='ms',tz='UTC').tz_convert(ET).tz_localize(None).floor('1min')
            dr=int(np.sign(r.new_bull)) if k=='new' else int(r.bull)
            if t in idx and dr:
                FL.append(dict(day=day,flag=k,t=t,dir=dr,pts=r30.get(t,np.nan)*dr,rand=base[day]*dr))
    # bursts frame: direction = sign(b)
    for r in bu.itertuples():
        t=pd.Timestamp(r.ts_ms,unit='ms',tz='UTC').tz_convert(ET).tz_localize(None); dr=int(np.sign(r.b))
        if t in idx and dr: FL.append(dict(day=day,flag='burst-strike',t=t,dir=dr,pts=r30.get(t,np.nan)*dr,rand=base[day]*dr))
    # ES / SPY flow vs SPX, 5-min bars
    for mkt,fn,mult in (('ES','x_es_prints',50.),('SPY','x_spy_prints',100.)):
        if not os.path.exists(Z+fn+'.parquet'): continue
        x=pd.read_parquet(Z+fn+'.parquet'); x=x[x.valid.astype(bool)&~x.eth.astype(bool)&~x.spread_leg.astype(bool)&(x.aggr!=0)]
        if mkt=='SPY':  # 0DTE only
            x=x[x.sym.str.contains(pd.Timestamp(day).strftime('%y%m%d'))]
        x['t']=pd.to_datetime(x.ts_ms,unit='ms',utc=True).dt.tz_convert(ET).dt.tz_localize(None)
        x=x[(x.t>=idx[0])&(x.t<=idx[-1]+pd.Timedelta('59s'))]
        if len(x)<100: continue
        T=np.full(len(x),3/365/24)  # crude: ~hours to expiry not used; use moneyness only via implied_delta w/ T guess
        end=pd.Timestamp(day+' 16:00').tz_localize(ET).value//10**6
        T=np.maximum(end-x.ts_ms.values,60000)/(365.25*86400e3)
        dl=implied_delta(x.px.values.astype(float),x.und.values.astype(float),x.strike.values.astype(float),T,x.cp.values.astype(float))
        x['nd']=np.sign(x.aggr)*np.sign(x.cp)*np.nan_to_num(dl)*x['size']*mult*x.und
        g=x.set_index('t').nd.resample('5min').sum()
        sp5=spot.resample('5min').last(); ret=sp5.diff()
        J=pd.DataFrame({'f':g,'r':ret}).dropna()
        J['rn']=J.r.shift(-1)
        XC.append(dict(day=day,mkt=mkt,n=len(x),bars=len(J),same=J.f.corr(J.r),nxt=J.f.corr(J.rn)))
F=pd.DataFrame(FL); F.to_pickle(S+'/work/flags.pkl')
F['edge']=F.pts-F.rand
print('\nUNUSUAL flags (SPX 0DTE single-leg, drop mid + drop crosses, tab defaults), SPX 30 min later in flag direction:')
print(F.groupby('flag').apply(lambda g: pd.Series(dict(n=g.pts.notna().sum(),right=(g.pts.dropna()>0).mean(),avg=g.pts.mean(),rand=g.rand.mean(),edge=g.edge.mean(),days_pos=f"{(g.groupby('day').edge.mean()>0).sum()}/{g.day.nunique()}"))).round(2).to_string())
print('today:'); print(F[F.day=='2026-11-24'].groupby('flag').apply(lambda g: pd.Series(dict(n=g.pts.notna().sum(),right=(g.pts.dropna()>0).mean(),avg=g.pts.mean(),edge=g.edge.mean()))).round(2).to_string())
X=pd.DataFrame(XC); print('\nES/SPY 5-min net delta$ vs SPX:'); print(X.round(2).to_string(index=False)); print(X.groupby('mkt')[['same','nxt']].mean().round(2))
