# L34 — "price walks into a warm Tetris block = reversal" (user circles, Fri 23 Oct A/E screens). Locked 25 Oct BEFORE scoring.
Days: the 12 sessions with open interest on file — 6–20 Oct (OI history) + 21 Oct. (The other history days have no OI.)
Field: Tetris A (OI×γ) and E (OI×vega), 0DTE, OI = morning OI (daily candle of the evening before), IV = prior-day IV per
contract, strikes = 5-pt grid ±100 around the 09:30 price, 10-min buckets 09:30–16:00, CAUSAL (v0.19): each strike scaled
to its running peak, colour bands from the quantiles of all values so far (AG 16 Oct shares).
Event: at the END of a bucket, the strike nearest SPX is warm (band ≥ 4 = red/orange/tan) and in the previous bucket the
strike nearest SPX was not warm → "entered a warm block". Direction = FADE the last 30-min move (−sign of S(t) − S(t−30));
skip if |move| < 3 pts. 30-min cooldown. First event from 10:00.
Score: SPX points 10/20/30 min later in that direction, minus 200 random same-day same-direction entries; t-stat; per-day signs.
Pass = edge > 0 at 20 min with t ≥ 2 on BOTH A and E and ≥ 60 % of days with events positive. Otherwise: no edge.
