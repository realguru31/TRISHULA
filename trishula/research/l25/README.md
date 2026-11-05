# L25 — AG Tetris 21 Oct (caption "they wanted some puts before the dip")
Target: AG screenshot re-gridded (labels CENTRAL time; 04:20 CT at x=454, 47.5 px/h; y = 15037 − 1.913·S − 0.0068·x,
fitted on AG's white price line vs our spot: median error 1.4 px ≈ 1 pt). Window 20:20–10:20 ET, strikes 7590–7850.
Caption, from the tape (1-min candles, 0DTE): 09:40–10:00 calls 7800–7815 SOLD ~2:1 (net −965, −814, −717, −331, −464 per
5 min) with SPX flat ~7734; puts 7715–7735 net BOUGHT (+535, +358, +824 at 10:00); dip to 7711 at 10:11; puts net SOLD at the
low (−713). Circled tan block (7790–7880, 06–09 ET): no unusual flow (balanced, below the overnight pace) → positioning.
Brute force (25,256 scored: iv snapshot/live × per-strike/price-grid × 6 greeks × 4 expiry sets × 7 weights × 4 sides × 7 norms):
  best: LIVE IV · PRICE GRID · γ · (OI + traded since 20:15) · C+P · each time column scaled to its peak
        0DTE 0.71/0.42 · +1DTE 0.70/0.47 · 0DTE→Fri 0.68/0.51 · all 6 expiries 0.64/0.54 (overall / over time)
  + 2 × net-put-flow γ field (0DTE): 0.70 / 0.53
  baseline (distance from spot) 0.56 / 0.15 · our current Tetris A (0DTE OI×γ per-strike peak) −0.04 / 0.20
Same family was top-3 on 20 Oct (price grid · γ · OI+traded · time-peak 0.80 / 0.34). AG's vertical columns still unexplained.
