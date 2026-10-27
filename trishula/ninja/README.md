# TrishulaSignals — NinjaTrader 8 indicator (v4)
Reads the TRISHULA feed and draws the Signals-view marks (S1, S3–S7) plus the VS3D Book (key levels, straddle band,
dealer net-contracts profile) at ES prices on any chart (ES recommended).

## Install
1. NinjaTrader 8 → New → NinjaScript Editor → right-click "Indicators" → New Indicator → name it `TrishulaSignals`
   → Finish. Replace ALL of the generated code with the contents of `TrishulaSignals.cs` → Compile (F5).
   (If it shows compile errors, copy them to Claude.)
2. On a chart (ES 1-minute is ideal) → Indicators → TrishulaSignals → set **Feed URL** to
   `https://trishula.streamlit.app/~/+/app/static/dtsignals_<your SIGNALS_KEY>.json`

## Settings
- Sensitivity: Fewer / Middle / More · Tape: 0DTE / 0+1DTE (same as the app's Signals view)
- One switch per signal (S1, S3, S4, S5, S6, S7) · "Only signals that passed the test" (default ON → today S6 only)
- Place at ES level (default): arrow at SPX × ES/SPX of that minute, else at the bar's high / low · offset in ticks
- Poll every N seconds (default 30) · colours · status text (feed time, STALE warning, last signal)

## Book (group "4. Book")
- Key levels UP TEST / DN TEST / BALANCE — DASHED = PREVIEW (yesterday's book, before 09:35 ET), SOLID = LOCKED for the
  session. Labels show the ES price and the SPX level it came from.
- Straddle band (dotted): spot ± ATM straddle, moves with spot.
- Profile on the right edge: dealer NET CONTRACTS per strike (green = dealer long, red = dealer short, brighter = more
  confident), numbers = contracts · SPX strike. Width / opacity / numbers / line width / colours adjustable.
- The Book is the CURRENT book (no history) — it is painted live, never stored as drawing objects.

## Notes
- The signal is known at the END of its minute → drawn on the bar that closes one minute after the mark's time.
- Times in the feed are ET; converted to NinjaTrader's time zone (Tools → Options → General).
- The feed refreshes every 60 s during RTH. If the app is asleep the status shows STALE.
