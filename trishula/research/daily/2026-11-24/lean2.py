import sys; sys.path.insert(0,sys.argv[1]); from common import *
ds=days()
rules=dict(LN.LOCKED); rules['E']=E
rng=np.random.default_rng(7)
res={}
for nm,r in rules.items():
    per=[];pa=[];nt=[]
    for d in ds:
        t=LN.run_rule(d,r); ta=LN.run_rule(d,r,'all')
        per.append(t.net.sum()); pa.append(ta.net.sum()); nt.append(len(t))
    nulls=[]
    for _ in range(200):
        s=0
        for d in ds:
            n=len(LN.bars(d,r['flow'],'single-leg',r['bar']))
            s+=LN.run_rule(d,r,shift=int(rng.integers(n//4,3*n//4))).net.sum()
        nulls.append(s)
    res[nm]=(per,pa,nt,nulls)
    tot=sum(per)
    print(f"{nm}: tot {tot:+.1f} per-day {tot/len(per):+.1f} up {sum(x>0 for x in per)}/{len(per)} trades {sum(nt)} ({np.mean(nt):.0f}/d) | all-prints {sum(pa):+.1f} | null p50 {np.percentile(nulls,50):+.1f} p95 {np.percentile(nulls,95):+.1f} pctile {np.mean(np.array(nulls)<tot)*100:.0f}% | today {per[-1]:+.1f} (all {pa[-1]:+.1f}, {nt[-1]} tr)")
print('day', *rules.keys())
for i,d in enumerate(ds): print(d['day'], *[f"{res[k][0][i]:+.1f}" for k in rules], ' all:', *[f"{res[k][1][i]:+.1f}" for k in rules])
json.dump({k:[list(map(float,v[0])),list(map(float,v[1])),v[2]] for k,v in res.items()},open(S+'/work/lean_res.json','w'))
# E plateau scan (src=bar: window inert). Also roll-src variant for window scan.
print('\nE scan X x cooldown (single-leg total, all days):')
Xs=[0.10,0.125,0.15,0.175,0.20]; cs=[5,7,10,12,15]
print('X\\cool',*cs)
for X in Xs:
    row=[]
    for c in cs:
        r=dict(E,X=X,cool=c); row.append(sum(LN.run_rule(d,r).net.sum() for d in ds))
    print(X,*[f"{v:+.0f}" for v in row])
print('\nE with conf OFF (=D):', sum(LN.run_rule(d,dict(E,conf=False)).net.sum() for d in ds))
print('\nwindow scan if lean = rolling window (src=roll, band X0.15, conf, cool10):')
for w in [10,15,20,25,30]:
    for X in [0.10,0.15,0.20]:
        r=dict(E,src='roll',win=w,X=X); v=[LN.run_rule(d,r).net.sum() for d in ds]
        print(f" win{w} X{X}: {sum(v):+.0f} up {sum(x>0 for x in v)}/{len(v)} trades {sum(len(LN.run_rule(d,r)) for d in ds)}")
