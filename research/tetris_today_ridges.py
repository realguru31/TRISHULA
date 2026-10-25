import sys, datetime as dt
sys.path.insert(0,"/home/claude/trishula")
import numpy as np, pandas as pd, plotly.io as pio
from core import spikes as SP, ridges_ag as RA
T="/tmp/claude-0/-home-claude/dee3bb00-9e12-54e5-970a-89cb0441116b/scratchpad/today"
c=pd.read_parquet(f"{T}/candles.parquet"); c=c[c.ts_ms<2e12].drop_duplicates(["sym","ts_ms"],keep="last")
c["t"]=pd.to_datetime(c.ts_ms,unit="ms",utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
o=c[c.sym.str.startswith(".SPXW")].copy(); o["base"]=o.sym.str.split("{").str[0]
o["strike"]=o.base.str[-4:].astype(float); o["cp"]=o.base.str[11].map({"C":1,"P":-1})
o[["bidv","askv"]]=o[["bidv","askv"]].fillna(0)
mt=pd.DataFrame({"m":o.t,"sym":o.base,"strike":o.strike,"cp":o.cp,"size":o.volume,"prem":o.volume*o.close*100,"net":o.askv-o.bidv})
mt=mt[mt["size"]>0]
spk,_=SP.detect(mt, dt.date(2026,10,20), {})
spx=c[c.sym.str.startswith("SPX{")].set_index("t").sort_index().close
es=c[c.sym.str.startswith("/ES")].set_index("t").sort_index().close
j=pd.concat([es.rename("es"),spx.rename("spx")],axis=1,sort=True).dropna(); basis=float((j.es-j.spx).median())
sp=(es-basis); sp.update(spx); bars=pd.DataFrame({"t":sp.index,"c":sp.values})
t0,t1=pd.Timestamp(sys.argv[1]),pd.Timestamp(sys.argv[2])
ks=[float(k) for k in range(7640,7815,5)]
pin=(7750.0,-1)
q=o[(o.strike==7750)&(o.cp==-1)].set_index("t").sort_index()
idx=pd.date_range(t0,t1,freq="1min")
px=q["close"].reindex(q.index.union(idx)).ffill().reindex(idx).dropna(); vol=q["volume"].reindex(idx).fillna(0)
sk=spk[(spk.strike==7750)&(spk.cp==-1)&(spk.m>=t0)&(spk.m<=t1)]
marks=[(r.m,f"⚡ {int(r.size)}c {r.side} ${r.prem/1e3:,.0f}k",RA.direction(-1,r.side)) for r in sk.itertuples()]
cd=[dict(px=px,vol=vol,marks=marks,cp=-1,name="7750P",header=f"Oct 20 7,750 P ${px.iloc[-1]:.2f} · vol {int(vol.sum()):,} · ⚡ {len(marks)}")]
f=RA.figure(mt,spk,bars,t0,t1,ks,pin=pin,side="C+P",top=1,contract=cd,h=900,title=f"TRISHULA ridges · today {t0:%H:%M}–{t1:%H:%M} ET · pinned 7750P",
            rth_open=pd.Timestamp("2026-10-20 09:30"))
pio.write_html(f,f"proto/{sys.argv[3]}.html",include_plotlyjs=True)
print("basis",basis,"spikes in window",int(((spk.m>=t0)&(spk.m<=t1)).sum()))
print(spk[(spk.m>=t0)&(spk.m<=t1)].assign(sc=lambda d:d.prem*d.z.fillna(4).clip(1,10)).nlargest(8,"sc")[["m","strike","cp","size","prem","z","side"]].to_string())
