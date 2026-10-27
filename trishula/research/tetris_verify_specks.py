import sys; sys.path.insert(0,"/home/claude/trishula")
from oi_model import *
from core import tetris as TT
legs=grid.groupby(["strike","cp"]).agg(oi=("oi","first"),iv=("iv","median")).reset_index()
legs["sym"]=[f"{k}_{cp}" for k,cp in zip(legs.strike,legs.cp)]
S=spot.groupby(spot.index.floor("10min")).last().reindex(idx).ffill().bfill()
# overlay: cumulative traded (buy+sell+unknown=vol) since session open
g=grid.copy(); g["sym"]=[f"{k}_{cp}" for k,cp in zip(g.strike,g.cp)]
ov=g.pivot_table(index="b",columns="sym",values="vol",aggfunc="sum").reindex(idx).fillna(0).cumsum()
for model in ("A","E"):
  for name,o in (("OI only",None),("OI+traded",ov)):
    M=TT.greek_field(legs,S,pd.Timestamp("2026-10-16 16:00"),model,o)
    M=M.loc[(M.index>=7600)&(M.index<=8050)]
    V=TT.per_strike_peak(M); B=TT.bands(V,"AG"); sk=TT.specks(V,B,S)
    first=sk.groupby(["strike","first_t"]).agg(last=("t","max"),n=("t","size")).reset_index().sort_values("first_t") if len(sk) else sk
    print(f"== model {model} · {name}: {len(first)} speck runs")
    if len(first): print(first.to_string(index=False))
print("SPX path:", spot.resample("30min").last()["2026-10-16 09:00":"2026-10-16 12:30"].round(1).to_dict())
