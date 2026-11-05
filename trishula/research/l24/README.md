# L24 research — turns / fades from the ridge data (11 sessions: 6–9, 12–16, 19, 20 Oct 2026, RTH)
Forward event study, causal features (data up to the minute), 10-min cooldown, outcome = SPX 10/20/30 min later.
978 configurations (absorption, initiation, chase, exhaustion, momentum, flow-contrarian, DT follow/fade ×
activity gates). Holdout: choose on 6–13 Oct, test on 14–20 Oct → most "best" configs FAILED (train/test r=0.17;
6–13 range-bound favoured fading, 14–20 trending favoured following).
Survived both halves (pts over next 20 min):
- initiation → follow (10-min net flow ≥ 5 % of volume, price ±4): +1.08 / +2.59 (4/4 test days)
- exhaustion + breadth → fade (15-min move ≥ 8, ≥ 5 unusual strikes): ≈ +0.4 / +1.1 (noisy, small n)
- DT + price confirms → follow (net squares ≥ 20 in 10 min, price ≥ 6): +0.84 / +2.02
- DT + price stalls (absorbed) → fade (net squares ≥ 40 in 5 min, price ≤ 1): +1.40 / +0.37
- plain DT follow loses (only 17 % of settings positive in both halves)
Hit rates 47–60 %: edges come from bigger winners, not frequency. Not a turn oracle; needs more days.

## DT thresholds (dtgrid.py, dtgrid2.py)
User defaults (band 5 % of dot, floor 200, ±0.75 %, watch 10): ~150 squares/h; follow +0.68 / −0.59, absorbed fade −0.83 / +0.54
(top 10 %, pts/20 min, week 6–13 / 14–20). "band % of dot" is inert: overnight dots are small, the floor sets the band
(band 3→15 % changes squares < 3 %). Threshold grid (576/rule): ~6 % of settings positive both weeks = chance.
Adaptive band = max(floor, α × strike's own last-30-min volume): squares 143 → 12/h; settings positive both weeks
18–38 % (best with 3-strike agreement) vs 7–13 % for the dot band. Best robust: follow, α 0.25, ±0.3 %, ≥2 net squares
in 3 min: +1.5 / +1.4 and +1.2 / +2.4 (hit 0.62 / 0.38). Delta-weighted adaptive, floor 800, absorbed fade: 3.6 squares/h,
+1.0 / +2.8, hit 0.54 / 0.65 (n 90 / 17).

## More DT ideas (20 Oct evening)
- off-pattern squares only (calls bought above / puts bought below spot): flips between weeks — rejected
- price-efficiency regime switch (follow when trending, fade when chopping): week 2 +1.5…+2.8, week 1 negative — rejected
- per-strike cooldown + one label per burst (idea3.py):
  v2 plain follow (≥2 net strikes / 3 min) is robust at every cooldown; 10-min cooldown best balance +1.76 / +2.69, days 5/6 · 4/5
  your DT: "absorbed → fade" at ≥3 net strikes is the only robust reading (+0.35 / +2.38; with 5-min cooldown +0.69 / +4.83, small n)
  one-label confirm/absorb on v2 leaves too few signals
- pending data (trishula_oi_history_dump.py): GEX regime switch (idea 1), filled/hollow vs next-morning OI on 1DTE (idea 2)

## OI history (trishula_oi_history.zip, 11 sessions)
Calibration: a daily candle's open interest = OI at the start of the NEXT session (candle labelled the evening
before); it equals the Summary OI exactly (r = 1.000 every day).
Idea 1 — dealer gamma (naive GEX from morning 0DTE OI, re-evaluated at each minute's spot):
  textbook switch (fade in +GEX, follow in −GEX): worst rule, never positive in both weeks.
  In −GEX DT is whipsawed (follow lost 2–5 pts per signal on 14, 15, 20 Oct). In +GEX following DT works:
  "follow DT only when GEX > 0" positive both weeks in 58 % of settings (best of any rule);
  classic DT ≥2 strikes +0.34 / +1.44 (7/9 days); v2 ≥2 strikes +0.68 / +4.79 (n 35 / 8).
Idea 2 — filled (extending) vs hollow (unwinding) vs next-morning OI on 1DTE contracts (575 contracts):
  OI rose on 81 % of traded 1DTE contracts regardless; "hollow" contracts rose 79 % of the time, "filled" 83 %
  → the label carries no information (accuracy 71 % < 81 % base). Per strike (DT netting): filled 85 % up,
  hollow 79 % up. Caveat: the day before expiry is an accumulation day; 0DTE cannot be checked (no next OI).
