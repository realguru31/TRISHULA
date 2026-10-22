import numpy as np, pandas as pd, glob, warnings; warnings.filterwarnings("ignore")
OIH="/tmp/claude-0/-home-claude/dee3bb00-9e12-54e5-970a-89cb0441116b/scratchpad/oih"
_t=lambda ms: pd.to_datetime(ms,unit="ms",utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
rows=[]
for d in sorted(glob.glob(f"{OIH}/2026*")):
    meta=pd.read_json(f"{d}/meta.json",typ="series"); D=pd.Timestamp(meta.day); N=str(meta.next_expiry)
    c=pd.read_parquet(f"{d}/candles.parquet"); lg=pd.read_parquet(f"{d}/legs.parquet"); sm=pd.read_parquet(f"{d}/summary.parquet")
    c["base"]=c.sym.str.split("{").str[0]; c=c.merge(lg,left_on="base",right_on="sym",suffixes=("","_l")); c=c[c.exp==N]
    dd=c[c.sym.str.contains(r"\{=1?d",regex=True)].copy(); dd["sess"]=(_t(dd.ts_ms)+pd.Timedelta(days=1)).dt.normalize()   # candle labelled the evening before its session
    mm=c[c.sym.str.contains("=m")].copy(); mm["t"]=_t(mm.ts_ms); mm=mm[(mm.t>=D+pd.Timedelta("9:30:00"))&(mm.t<=D+pd.Timedelta("16:15:00"))]
    for col in ("bidv","askv"): mm[col]=mm[col].fillna(0)
    # OI before session D = daily candle for session D ; after = Summary (morning of N; N expired or current)
    before=dd[dd.sess==D].groupby("base").oi.last()
    after=sm.set_index("sym").oi
    # dot: participant net (askv−bidv) on all days BEFORE D from daily candles ; mv = net on D from 1-minute candles
    dot=dd[dd.sess<D].assign(n=lambda z:(z.askv.fillna(0)-z.bidv.fillna(0))).groupby("base").n.sum()
    mv=mm.assign(n=mm.askv-mm.bidv).groupby("base").n.sum(); vol=mm.groupby("base").volume.sum()
    t=pd.DataFrame({"oi0":before,"oi1":after,"dot":dot,"mv":mv,"vol":vol}).dropna(subset=["oi0","oi1"]).fillna(0)
    t=t.join(lg.set_index("sym")[["strike","cp"]]); t["day"]=meta.day
    rows.append(t)
T=pd.concat(rows); T["doi"]=T.oi1-T.oi0
T=T[T.vol>=50]
print("contracts:",len(T),"days:",T.day.nunique())
# per contract: DT label at end of day (contract level, participant view: bought + / sold −)
floor=200
T["label"]=np.where(T.mv.abs()<floor,"no square",np.where((T["dot"].abs()<floor)|(np.sign(T["dot"])==np.sign(T.mv)),"filled (extending)","hollow (unwinding)"))
T["oi_up"]=T.doi>0
print(T.groupby("label").agg(n=("doi","size"),share_OI_up=("oi_up","mean"),median_dOI=("doi","median")).round(2).to_string())
# better test: does the sign of net flow vs dot explain dOI? also |mv| vs dOI
T["pred"]=np.where(T.label.str.startswith("filled"),1,np.where(T.label.str.startswith("hollow"),-1,0))
k=T[T.pred!=0]; print("\nfilled→OI up / hollow→OI down accuracy:", round(((k.pred>0)==(k.doi>0)).mean(),3), "base rate OI up:", round((T.doi>0).mean(),3))
# alternative classifier: opening if customer net and dealer... use volume: share of volume that becomes new OI
T["open_share"]=T.doi/T.vol
print("\nmedian ΔOI / volume:", round(T.open_share.median(),3), "· share of contracts where ΔOI<0:", round((T.doi<0).mean(),3))
# per strike (C−P netted like DT)
S_=T.assign(nf=np.where(T.cp==1,1,-1)*T.mv, nd=np.where(T.cp==1,1,-1)*T["dot"]).groupby(["day","strike"]).agg(nf=("nf","sum"),nd=("nd","sum"),doi=("doi","sum"))
S_["label"]=np.where(S_.nf.abs()<floor,"none",np.where((S_.nd.abs()<floor)|(np.sign(S_.nd)==np.sign(S_.nf)),"filled","hollow"))
print("\nper strike (DT's own netting):"); print(S_.groupby("label").agg(n=("doi","size"),share_OI_up=("doi",lambda s:(s>0).mean())).round(2).to_string())
T.to_pickle("idea2.pkl")
