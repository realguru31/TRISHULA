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
