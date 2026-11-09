# TrishulaSignals (NinjaTrader 8 indicator) — changelog

Semantic versioning, separate from the app. The version shows on the chart (indicator label and status line) and in
`IndicatorVersion` at the top of the class. Every change to `TrishulaSignals.cs` bumps it here.

## 7.1.0 — 2 Nov 2026 (app v0.23.0)
- Single-leg levels, dotted: SL UP dodger blue, SL DN magenta, SL BAL yellow (faded = preview); own switch + colours.
- Status line: single-leg locked hh:mm / preview.

## 7.0.0 — 28 Oct 2026 (app v0.22.0)
- Book profile: 09:35 dots + grey move-since-lock line; with dots ON a zero line in the middle (right = dealer long).
- Single-leg (clean-B) profile on the left edge (blue = dealer +, magenta = −); level labels move right of it.
- Version shown on the chart.

## 6.0.0 — 27 Oct 2026 (app v0.21.2)
- Status line shows where the 09:35 lock came from (restored after restart / ⚠ LATE LOCK).

## 5.0.0 — 27 Oct 2026 (app v0.21.1)
- Signal arrows, labels and status painted in OnRender (drawing objects went missing after some reloads). Arrow size.

## 4.0.0 — 27 Oct 2026 (app v0.21.0)
- VS3D Book at ES prices: key levels (dashed preview / solid locked), straddle band, dealer net-contracts profile.

## 3.0.0 — 27 Oct 2026 (app v0.20.3)
- Draws only in OnBarUpdate when the feed changed (no chart reload); labels glued to arrows by pixel offset.

## 2.0.0 — 27 Oct 2026 (app v0.20.2)
- Overnight (GTH) marks, own colours; chart label "TRISHULA" (no URL); only new marks drawn.

## 1.0.0 — 27 Oct 2026 (app v0.20.0)
- First version: Signals-view marks (S1, S3–S7) from the JSON feed at ES levels; sensitivity / tape / per-signal filters.
