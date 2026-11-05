import numpy as np, pandas as pd, warnings; warnings.filterwarnings("ignore")
L="/tmp/claude-0/-home-claude/dee3bb00-9e12-54e5-970a-89cb0441116b/scratchpad/l21/"
def zigzag(s, th):
    v=s.values; idx=s.index; piv=[]; d=0; ext=0; start=0
    for i in range(1,len(v)):
        if d>=0 and v[i]>v[ext] or d<=0 and v[i]<v[ext]:
            if d==0: d=1 if v[i]>v[start] else -1
            ext=i
        elif abs(v[i]-v[ext])>=th:
            piv.append((idx[ext], 'top' if d>0 else 'bottom', v[ext])); d=-d; ext=i
    return pd.DataFrame(piv,columns=["t","kind","px"])
def load(day):
    if day=="20oct":
        o=pd.read_pickle(L+"opt.pkl"); s=pd.read_pickle(L+"spot.pkl"); end="2026-10-20 11:24"; start="2026-10-20 07:00"
    else:
        o=pd.read_pickle(L+"opt16.pkl"); s=pd.read_pickle(L+"spot16.pkl"); end="2026-10-16 15:59"; start="2026-10-16 07:00"
    allm=pd.date_range(o.t.min().floor("1min"),end,freq="1min")
    s=s.reindex(allm).ffill()
    return o,s,allm,pd.Timestamp(start),pd.Timestamp(end)
def per_strike(o, allm, col):
    x=o.pivot_table(index="t",columns=["strike","cp"],values=col,aggfunc="sum").reindex(allm).fillna(0)
    return x
