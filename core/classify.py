"""Five-bucket print classifier (AG-REV spec section 5).

Every print is judged against the bid/ask DXLink attaches to it.
Buckets: 0 BELOW_BID, 1 BID, 2 MID, 3 ASK, 4 ABOVE_ASK, 9 UNCLASSIFIED.
"""
import math

BELOW_BID, BID, MID, ASK, ABOVE_ASK, UNCLASSIFIED = 0, 1, 2, 3, 4, 9
NAMES = {0: "BELOW_BID", 1: "BID", 2: "MID", 3: "ASK", 4: "ABOVE_ASK", 9: "UNCLASSIFIED"}


def tick_for(price: float) -> float:
    """SPX option tick: 0.05 below $3.00, 0.10 at or above."""
    return 0.05 if price < 3.0 else 0.10


def _ok(x) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x)) and x > 0


def bucket(p: float, b: float, a: float) -> int:
    if not (_ok(p) and _ok(b) and _ok(a)) or a < b:
        return UNCLASSIFIED
    eps = tick_for(p) / 2
    if p > a + eps:
        return ABOVE_ASK
    if abs(p - a) <= eps:
        return ASK
    if p < b - eps:
        return BELOW_BID
    if abs(p - b) <= eps:
        return BID
    return MID


def aggr(bk: int, p: float, b: float, a: float, mid_weight: float = 0.0,
         aggressor: str | None = None, use_aggressor: bool = True) -> float:
    """Signed customer direction: +1 bought, -1 sold, MID weighted, 0 unknown."""
    if bk in (ASK, ABOVE_ASK):
        return 1.0
    if bk in (BID, BELOW_BID):
        return -1.0
    if bk == MID:
        if use_aggressor and aggressor in ("BUY", "SELL"):
            return mid_weight * (1.0 if aggressor == "BUY" else -1.0)
        mid = (a + b) / 2
        return mid_weight * (1.0 if p > mid else -1.0 if p < mid else 0.0)
    return 0.0
