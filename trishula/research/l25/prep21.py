import sys; sys.path.insert(0,"/tmp/claude-0/-home-claude/dee3bb00-9e12-54e5-970a-89cb0441116b/scratchpad/l25")
import numpy as np, pandas as pd
from pipe import _t, fit_axes, target
D="/tmp/claude-0/-home-claude/dee3bb00-9e12-54e5-970a-89cb0441116b/scratchpad/d21/"
c=pd.read_pickle(D+"candles.pkl"); c=c[c.ts_ms<2e12]
es=c[c.sym.str.startswith("/ES")].drop_duplicates("ts_ms").set_index("ts_ms").close
sx=c[c.sym.str.startswith("SPX{")].drop_duplicates("ts_ms").set_index("ts_ms").close
j=pd.concat([es.rename("es"),sx.rename("spx")],axis=1).dropna(); bas=float((j.es-j.spx).median()); print("basis",round(bas,2),len(j))
s=es-bas; s.index=_t(pd.Series(s.index)).values; s=s.sort_index().resample("1min").last().ffill()
sxx=sx.copy(); sxx.index=_t(pd.Series(sxx.index)).values; ii=sxx.index.intersection(s.index); s.loc[ii]=sxx.loc[ii].values
s=s["2026-10-20 20:00":]; s.to_pickle("spot21.pkl"); print(s.resample("2h").last().round(1).to_dict())
p=pd.read_pickle("path21_px.pkl")
best=fit_axes(p,s,"2026-10-21 04:20",420,np.arange(40,56,0.5),range(396,446,2)); print("fit",best)
