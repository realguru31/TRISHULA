import sys; sys.path.insert(0,sys.argv[1]); from common import *
ds=days(); R=dict(LN.LOCKED); R['E']=E
def gated(d,r):
    b=LN.bars(d,r['flow'],'single-leg',r['bar']); col,_=LN.colours(b,**r)
    tm=b.index.strftime('%H:%M'); c=b.c.values; pos=0; out=0.0; px=0
    for i in range(len(c)):
        w=col[i]; ok=('10:00'<=tm[i]<='14:59')
        if i==len(c)-1: tgt=0
        elif w==0: tgt=pos
        elif w==pos: tgt=pos
        else: tgt= w if ok else 0   # opposite colour: exit; only open new if inside window
        if tgt!=pos:
            if pos: out+=(c[i]-px)*pos-LN.COST
            pos,px=tgt,c[i]
    return out
print('N1 time gate (10:00-14:59 opens):')
for k in ('A','D','E'):
    u=[LN.run_rule(d,R[k]).net.sum() for d in ds]; g=[gated(d,R[k]) for d in ds]
    print(f" {k}: ungated {sum(u):+.1f}  gated {sum(g):+.1f}  gated better on {sum(gg>uu+1e-9 for gg,uu in zip(g,u))}/{len(ds)} days (ties {sum(abs(gg-uu)<1e-9 for gg,uu in zip(g,u))}) today {u[-1]:+.1f}->{g[-1]:+.1f}")
vix={'2026-11-05':16.61,'2026-11-09':25.64,'2026-11-10':19.92,'2026-11-11':19.46,'2026-11-12':17.49,'2026-11-16':19.30,'2026-11-17':22.91,'2026-11-18':25.46,'2026-11-20':28.44,'2026-11-23':35.89,'2026-11-24':26.62}
L=json.load(open(S+'/work/lean_res.json'))
print('N3 VIX prior close regime:')
for k in ('A','B','D','E'):
    per=L[k][0]; lo=[p for d,p in zip(ds,per) if vix[d['day']]<20]; hi=[p for d,p in zip(ds,per) if vix[d['day']]>=20]
    print(f" {k}: VIX<20 {len(lo)}d {sum(lo):+.1f} ({sum(x>0 for x in lo)} up) | VIX>=20 {len(hi)}d {sum(hi):+.1f} ({sum(x>0 for x in hi)} up)")
# N2
F=pd.read_pickle(S+'/work/flags.pkl'); F=F[F.flag=='new'].copy(); lean={d['day']:d for d in ds}
ag=[]
for r in F.itertuples():
    b=LN.bars(lean[r.day],'0DTE','single-leg',1); b=b[b.index<=r.t]; ag.append(int(np.sign((b.b-b.r).sum()))==r.dir)
F['agree']=ag; F['edge']=F.pts-F.rand
print('N2 new-position flags by session-lean agreement:')
print(F.groupby('agree').apply(lambda g: pd.Series(dict(n=g.pts.notna().sum(),right=(g.pts.dropna()>0).mean(),avg=g.pts.mean(),edge=g.edge.mean(),days_pos=f"{(g.groupby('day').edge.mean()>0).sum()}/{g.day.nunique()}"))).round(2).to_string())
