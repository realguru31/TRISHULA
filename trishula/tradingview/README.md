# TRISHULA Levels — TradingView indicator

Separate version from the app (header line of the .pine file). TradingView cannot read the live feed, so this is a
paste-per-day script: no live bars, no slider, no straddle.

## Install
TradingView → Pine Editor → new indicator → replace everything with `TRISHULA_Levels.pine` → Save → Add to chart.

## Daily
After 09:36 ET (both locks done): TRISHULA → VS3D → Book → "TradingView paste" → copy icon → paste into a free
"Day" field (settings of the indicator). 10 fields = 10 days, any order; clear the oldest to reuse it.
Upper-case M / S in the line = locked levels; lower-case = preview (pasted before the lock).

## Works on
SPX (levels as-is), ES / MES / SPX CFDs — converted with chart ÷ SPX of the latest bar where SPX prints.

## Changelog
- 1.0.2 — 1 Nov 2026: CFDs whose ticker is also "SPX" (Spreadex) get the conversion.
- 1.0.1 — 1 Nov 2026: future-dated (preview) day draws from the last bar; prices rounded to tick.
- 1.0.0 — 2 Nov 2026 (app v0.23.0): first version.
