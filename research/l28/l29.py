"""L29 locked test — six signals × tiers, fixed before the history arrived (queue 21 Oct 14:05–14:06)."""
import sys, glob, pickle, json
sys.path.insert(0, "/tmp/claude-0/-home-claude/dee3bb00-9e12-54e5-970a-89cb0441116b/scratchpad/l28")
sys.path.insert(0, "/home/claude/trishula")
import numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
from setup import wings, setup_signals
from core import dtv2 as V
B = "/tmp/claude-0/-home-claude/dee3bb00-9e12-54e5-970a-89cb0441116b/scratchpad"
_t = lambda ms: pd.to_datetime(ms, unit="ms", utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
rng = np.random.default_rng(7)


def opts(c, legs):
    o = c[c.sym.str.startswith(".SPXW")].copy(); o["base"] = o.sym.str.split("{").str[0]
    o = o.merge(legs[["sym", "exp", "strike", "cp"]], left_on="base", right_on="sym", suffixes=("_x", ""))
    o["t"] = _t(o.ts_ms); o[["bidv", "askv", "volume"]] = o[["bidv", "askv", "volume"]].fillna(0)
    return o[["t", "base", "exp", "strike", "cp", "volume", "bidv", "askv", "close"]]


def spx(c, day):
    s = c[c.sym.str.startswith("SPX{") & (c.ts_ms < 2e12)].drop_duplicates("ts_ms")
    s = pd.Series(s.close.values, index=_t(s.ts_ms).values).sort_index()
    rth = pd.date_range(f"{day} 09:30", f"{day} 15:59", freq="1min")
    return s.reindex(rth).ffill(), rth


def load_all():
    days = []
    for d in sorted(glob.glob(f"{B}/hist/2026*")):
        m = json.load(open(f"{d}/meta.json")); c = pd.read_pickle(f"{d}/candles.pkl"); lg = pd.read_pickle(f"{d}/legs.pkl")
        S, rth = spx(c, m["day"]); o = opts(c, lg)
        days.append(dict(day=m["day"], S=S, rth=rth, o=o))
    for x in pickle.load(open(f"{B}/md/days.pkl", "rb")):
        o = x["o"].rename(columns={"base": "base"}).copy(); o["exp"] = x["day"]
        days.append(dict(day=x["day"], S=x["S"], rth=x["rth"], o=o))
    c = pd.read_pickle(f"{B}/d21/candles.pkl"); ch = pd.read_pickle(f"{B}/d21/chain.pkl"); xc = pd.read_pickle(f"{B}/d21/xchain.pkl")
    S, rth = spx(c, "2026-10-21"); rth = rth[rth <= pd.Timestamp("2026-10-21 12:59")]; S = S.reindex(rth)
    o = opts(c, pd.concat([ch[["sym", "exp", "strike", "cp"]], xc[xc.exp == "2026-10-22"][["sym", "exp", "strike", "cp"]]]))
    days.append(dict(day="2026-10-21", S=S, rth=rth, o=o))
    return sorted(days, key=lambda x: x["day"])


def cool(series, minutes=10):
    out = pd.Series(0, index=series.index); last = None
    for t, v in series[series != 0].items():
        if last is None or (t - last) >= pd.Timedelta(minutes=minutes):
            out[t] = int(np.sign(v)); last = t
    return out


# ── the six signals ──────────────────────────────────────────────────────────
def S1_blocks(x, k):
    """aggressive block against the move: one contract-minute, size ≥ max(100, k × its own prior median minute),
    ≥ 90 % at ask (bought) or bid (sold), against the last 15-min move; 0DTE + 1DTE."""
    o = x["o"]; S = x["S"]; sig = pd.Series(0, index=x["rth"])
    o = o[(o.t >= x["rth"][0]) & (o.t <= x["rth"][-1])].sort_values("t")
    med = o.groupby("base").volume.transform(lambda v: v.where(v > 0).expanding().median().shift(1))
    big = (o.volume >= np.maximum(100, k * med.fillna(np.inf)))
    bought = o.askv >= 0.9 * o.volume; sold = o.bidv >= 0.9 * o.volume
    d = np.where(bought, np.where(o.cp == 1, 1, -1), np.where(sold, np.where(o.cp == 1, -1, 1), 0))
    e = o[big & (d != 0)].assign(d=d[(big & (d != 0)).values])
    dp15 = S.diff(15)
    for t, g in e.groupby("t"):
        dd = int(np.sign(g.d.sum()))
        if dd and t in dp15.index and dp15[t] == dp15[t] and np.sign(dp15[t]) == -dd:
            sig[t] = dd
    return cool(sig)


def S2_setup(x, ratio):
    w = wings(x["o"][x["o"].exp == x["day"]], x["S"], x["rth"][0], x["rth"][-1])
    sg = setup_signals(w, x["S"], ratio=ratio, rng_max=15)
    s = pd.Series(0, index=x["rth"])
    for t, d, _ in sg.itertuples(index=False):
        if t in s.index: s[t] = d
    return cool(s)


def S3_flip(x, size):
    o = x["o"][x["o"].exp == x["day"]]; S = x["S"]
    o = o[(o.t >= x["rth"][0]) & (o.t <= x["rth"][-1])].copy()
    o["off"] = o.strike.values - S.reindex(o.t).values
    o = o[o.off.abs() <= 25]
    o["bull"] = np.where(o.cp == 1, 1, -1) * (o.askv - o.bidv)
    b = o.groupby(o.t.dt.floor("5min")).bull.sum()
    b = b.reindex(pd.date_range(x["rth"][0], x["rth"][-1], freq="5min")).fillna(0)
    s = pd.Series(0, index=x["rth"])
    for i in range(1, len(b)):
        if np.sign(b.iat[i]) != np.sign(b.iat[i - 1]) and abs(b.iat[i]) >= size and np.sign(b.iat[i - 1]) != 0:
            t = b.index[i] + pd.Timedelta(minutes=5)
            if t in s.index: s[t] = int(np.sign(b.iat[i]))
    return cool(s)


def _frames(x):
    o = x["o"][x["o"].exp == x["day"]]
    mt = pd.DataFrame({"m": o.t, "sym": o.base, "strike": o.strike, "cp": o.cp, "size": o.volume, "net": o.askv - o.bidv})
    return V.minute_frames(mt, x["rth"])


def S4_follow(x, need, cache):
    nf, vol = cache
    sq = V.squares(nf, vol, x["S"])
    return V.follow(sq, x["rth"], need=need)


def S5_init(x, share, cache):
    nf, vol = cache
    return V.initiation(nf, vol, x["S"], share=share)


def S6_exhaust(x, pts, cache):
    nf, vol = cache
    K = vol.columns.values.astype(float); Sv = x["S"].reindex(vol.index).ffill().values
    N = np.abs(K[None, :] - Sv[:, None]) <= 50
    b = vol.shift(1); med = b.rolling(30, min_periods=10).median(); mad = (b - med).abs().rolling(30, min_periods=10).median()
    Z = ((vol - med) / (1.4826 * mad + 1)).values
    br = pd.Series(((Z > 4) & N).sum(1), index=vol.index).rolling(5, min_periods=1).max()
    dp = x["S"].diff(15)
    s = pd.Series(np.where((br >= 5) & (dp >= pts), -1, np.where((br >= 5) & (dp <= -pts), 1, 0)), index=x["rth"])
    s[s.index < x["rth"][0] + pd.Timedelta(minutes=10)] = 0
    return cool(s)


SIGNALS = [("S1 aggressive block vs move", "×5", lambda x, c: S1_blocks(x, 5)), ("S1 aggressive block vs move", "×10", lambda x, c: S1_blocks(x, 10)),
           ("S1 aggressive block vs move", "×20", lambda x, c: S1_blocks(x, 20)),
           ("S2 loading setup", "1.4:1", lambda x, c: S2_setup(x, 1.4)), ("S2 loading setup", "1.6:1", lambda x, c: S2_setup(x, 1.6)),
           ("S2 loading setup", "2.2:1", lambda x, c: S2_setup(x, 2.2)),
           ("S3 near-spot flip", "500", lambda x, c: S3_flip(x, 500)), ("S3 near-spot flip", "1000", lambda x, c: S3_flip(x, 1000)),
           ("S3 near-spot flip", "2000", lambda x, c: S3_flip(x, 2000)),
           ("S4 DT v2 follow", "2 strikes", lambda x, c: S4_follow(x, 2, c)), ("S4 DT v2 follow", "3 strikes", lambda x, c: S4_follow(x, 3, c)),
           ("S4 DT v2 follow", "4 strikes", lambda x, c: S4_follow(x, 4, c)),
           ("S5 initiation", "5 %", lambda x, c: S5_init(x, 0.05, c)), ("S5 initiation", "10 %", lambda x, c: S5_init(x, 0.10, c)),
           ("S5 initiation", "15 %", lambda x, c: S5_init(x, 0.15, c)),
           ("S6 exhaustion+breadth", "8 pts", lambda x, c: S6_exhaust(x, 8, c)), ("S6 exhaustion+breadth", "12 pts", lambda x, c: S6_exhaust(x, 12, c)),
           ("S6 exhaustion+breadth", "16 pts", lambda x, c: S6_exhaust(x, 16, c))]


if __name__ == "__main__":
    D = load_all(); print(len(D), "sessions:", [x["day"] for x in D], flush=True)
    rows = []
    for x in D:
        S = x["S"]; cache = _frames(x)
        fw = {h: S.shift(-h) - S for h in (10, 20, 30)}
        for name, tier, fn in SIGNALS:
            try:
                sg = fn(x, cache)
            except Exception as e:                      # noqa: BLE001
                print("ERR", x["day"], name, tier, e); continue
            ev = sg[sg != 0]
            valid = fw[20].dropna().index
            for t, d in ev.items():
                if t not in valid: continue
                # random control: same day, same direction, same number — mean over 200 random valid minutes
                rnd = rng.choice(valid, size=200)
                rows.append(dict(day=x["day"], signal=name, tier=tier, t=t, d=int(d),
                                 r10=float(fw[10].get(t, np.nan) * d), r20=float(fw[20][t] * d), r30=float(fw[30].get(t, np.nan) * d),
                                 ctrl20=float(np.nanmean(fw[20].reindex(rnd).values) * d)))
        print(x["day"], "done", flush=True)
    R = pd.DataFrame(rows); R.to_pickle(f"{B}/l28/l29_events.pkl")
    days = sorted(R.day.unique()); half = days[:len(days) // 2 + 1]
    R["half"] = np.where(R.day.isin(half), "H1", "H2"); R["edge20"] = R.r20 - R.ctrl20
    def summ(g):
        return pd.Series(dict(n=len(g), days=g.day.nunique(), right=(g.r20 > 0).mean(), avg20=g.r20.mean(), edge20=g.edge20.mean(),
                              t=g.edge20.mean() / (g.edge20.std() / np.sqrt(len(g)) + 1e-9)))
    T = R.groupby(["signal", "tier"]).apply(summ)
    H = R.groupby(["signal", "tier", "half"]).edge20.mean().unstack()
    T = T.join(H.rename(columns={"H1": "edge H1", "H2": "edge H2"}))
    T["both halves +"] = (T["edge H1"] > 0) & (T["edge H2"] > 0)
    pd.set_option("display.width", 220)
    print(T.round(2).to_string())
    T.to_pickle(f"{B}/l28/l29_table.pkl")
