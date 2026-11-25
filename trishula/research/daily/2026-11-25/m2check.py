"""M2 robustness (POST-HOC, written after seeing M2 = 11/12): price-only control and neighbourhood."""
import sys; sys.path.insert(0, sys.argv[1]); from common import *
from money_frame import frame
rows=[]
for d in days():
    s,r=frame(d); c=s.c; net=r.sb-r.sr; day=d['day']
    for w in (3,5,10,15):
        for H in (30,60,90):
            if w+H>=len(c): continue
            out=c.iloc[w+H]-s.o.iloc[w]
            rows.append(dict(day=day,w=w,H=H,money=np.sign(net.iloc[:w].sum()),price=np.sign(c.iloc[w-1]-s.o.iloc[0]),
                             all=np.sign((r.sb-r.sr).iloc[:w].sum()),out=out))
R=pd.DataFrame(rows)
R['hm']=(np.sign(R.out)==R.money); R['hp']=(np.sign(R.out)==R.price); R['pts']=R.out*R.money
print(R.groupby(['w','H']).agg(n=('hm','size'),money_hit=('hm','mean'),price_hit=('hp','mean'),money_pts=('pts','mean'),agree=('money',lambda x: (x==R.loc[x.index,'price']).mean())).round(2).to_string())
q=R[(R.w==5)&(R.H==60)]; print(q[['day','money','price','out']].to_string(index=False))
