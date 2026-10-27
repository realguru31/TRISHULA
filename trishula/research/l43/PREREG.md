# L43 — AG-scale Tetris, CAUSAL (what a trader sees at each moment). Locked 25 Oct 15:10 ET before scoring.
Days: 12 with OI (6–20 Oct + 21 Oct). Tetris A and E, 0DTE, 10-min buckets, RTH. At every step t (10:00 → 15:30) the
chart is rebuilt with data up to t: each strike ÷ its max over 09:30…t, AG colour shares over all cells up to t.
V1 "price into heat": at t the strike nearest SPX is warm (band ≥ 4) in the LATEST column and was not at t−10 →
   fade the last 30-min move (skip |move| < 3).
V2 "turn confirmed": at t a cell within 10 pts of the last-30-min high (low) turns warm that was not warm at t−10 →
   short (long). Skip if the extreme is < 5 pts from price at t (no turn yet).
30-min cooldown per variant. Score SPX pts 10/20/30 min after t vs the day's average same-direction move.
PASS = edge20 > 0, t ≥ 2 for both A and E, ≥ 60 % of days with events positive.
