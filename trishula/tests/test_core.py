from core.classify import bucket, aggr, ASK, ABOVE_ASK, BID, BELOW_BID, MID, UNCLASSIFIED
from core.timeutil import recording_window, ET
from datetime import datetime

def test_buckets():
    assert bucket(10.10, 9.90, 10.10) == ASK
    assert bucket(10.30, 9.90, 10.10) == ABOVE_ASK
    assert bucket(9.90, 9.90, 10.10) == BID
    assert bucket(9.70, 9.90, 10.10) == BELOW_BID
    assert bucket(10.00, 9.90, 10.10) == MID
    assert bucket(1.00, 0, 1.1) == UNCLASSIFIED
    assert bucket(1.00, 1.2, 1.1) == UNCLASSIFIED      # crossed
    assert bucket(2.02, 1.95, 2.00) == ASK              # within half tick (0.025)

def test_aggr():
    assert aggr(ASK, 1, 0.9, 1) == 1 and aggr(BID, 1, 1, 1.1) == -1
    assert aggr(MID, 1, 0.9, 1.1) == 0                 # MidWeight 0
    assert aggr(MID, 1, 0.9, 1.1, 0.5, "BUY") == 0.5

def test_window():
    assert not recording_window(datetime(2026,10,17,12,0,tzinfo=ET))   # Saturday
    assert recording_window(datetime(2026,10,18,20,0,tzinfo=ET))       # Sunday night
    assert recording_window(datetime(2026,10,19,10,0,tzinfo=ET))       # Monday RTH
    assert not recording_window(datetime(2026,10,19,17,0,tzinfo=ET))   # maintenance gap
    assert not recording_window(datetime(2026,10,23,17,0,tzinfo=ET))   # Friday evening


def test_dsign_seed_and_anchor():
    import pandas as pd
    from core import signs
    t0 = signs.seed_from_ms("2026-10-19")
    p = pd.DataFrame({"ts_ms": [t0 + 1000, t0 + 2000], "sym": [".C", ".C"], "exp": ["2026-10-19"] * 2,
                      "strike": [7600.0] * 2, "cp": [1, 1], "ev_type": ["0", "0"], "aggr": [1, 1],
                      "size": [3, 1], "spread_leg": [False, True]})
    t = signs.dsign_table(p, pd.DataFrame(), {".C": ("2026-10-19", 7600.0, 1)}, "2026-10-19", t0 + 10**9)
    assert t.loc[0, "dsign"] == -1.0 and t.loc[0, "seed_tot"] == 4
    # later expiry anchors to the current session
    assert signs.seed_from_ms("2026-11-20", "2026-10-19") == t0


def _unu_day(day, seed):
    """synthetic single-leg 0DTE tape for one RTH session (for the unusual-flag tests)."""
    import numpy as np
    import pandas as pd
    from core import unusual as UN
    r = np.random.default_rng(seed)
    t0 = UN._t0(pd.Timestamp(day))
    n = 40_000
    ts = np.sort(t0 + r.integers(0, int(6.5 * 3600 * 1000), n))
    K = 7000 + 5 * r.integers(-20, 21, n)
    cp = r.choice([1.0, -1.0], n)
    S = 7000 + np.cumsum(r.normal(0, 0.05, n))
    px = np.maximum(0.05, np.abs(S - K) * (cp * (S - K) > 0) + 3 + r.random(n))
    bid, ask = px - 0.05, px + 0.05
    aggr = r.choice([1.0, -1.0], n)
    px = np.where(r.random(n) < 0.05, np.where(aggr > 0, ask + 0.05, bid - 0.05), np.where(aggr > 0, ask, bid))
    size = np.maximum(1, r.pareto(1.5, n) * 3).round()
    sym = [f".SPXW{day}{'C' if c > 0 else 'P'}{k}" for c, k in zip(cp, K)]
    return pd.DataFrame({"ts_ms": ts.astype("int64"), "sym": sym, "strike": K.astype(float), "cp": cp, "px": px, "size": size,
                         "bid": bid, "ask": ask, "aggr": aggr, "sl": np.ones(n, bool), "eth": np.zeros(n, bool), "S": S,
                         "oi": np.full(n, 300.0)})


def test_unusual_no_repaint():
    """v0.44.0: a flag decided at 11:00 is the same when the day is recomputed at 15:00 (nothing appears / vanishes)."""
    import pandas as pd
    from core import unusual as UN
    days = ["2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19"]
    hist = [UN.summary(_unu_day(d, i), "SPX", pd.Timestamp(d), exp=d) for i, d in enumerate(days[:3])]
    d = days[3]
    f = _unu_day(d, 9)
    p = dict(UN.DEF, drop_mid=False)
    cut = UN.cuts(hist, "single-leg", p)
    assert cut is not None and cut["n"] == 3
    cutoff = UN._t0(pd.Timestamp(d)) + 90 * 60_000                       # 11:00
    a, ba = UN.detect(f[f.ts_ms < cutoff], "SPX", pd.Timestamp(d), "single-leg", UN.FLAGS, p, exp=d, cut=cut)
    b, bb = UN.detect(f, "SPX", pd.Timestamp(d), "single-leg", UN.FLAGS, p, exp=d, cut=cut)
    key = lambda o, k: set(map(tuple, o.loc[o[k] & (o.ts_ms < cutoff), ["ts_ms", "sym"]].values))   # noqa: E731
    for k in ("big", "pay", "new", "burst"):
        assert key(a, k) == key(b, k), k
    assert sum(int(a[k].sum()) for k in ("big", "pay", "new")) > 0
    bm = lambda x: set(map(tuple, x.loc[x.ts_ms < cutoff, ["m", "k"]].values)) if len(x) else set()   # noqa: E731
    assert bm(ba) == bm(bb)
    # fewer than 3 previous sessions → no cut-off, big / paying up / bursts stay off
    assert UN.cuts(hist[:2], "single-leg", p) is None
