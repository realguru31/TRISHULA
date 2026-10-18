# TRISHULA changelog

Semantic versioning: MAJOR.MINOR.PATCH. The running version is shown in the app's
status bar, every tab footer, and the Recorder diagnostics panel.

## v0.2.0 — 2026-10-18
- Common control bar on top of every tab: expiry quick-pick (0DTE / 1DTE / Weekly / Monthly /
  Other = any listed expiry) and strike window (± N strikes or ± % move).
- Any expiry can be viewed: the recorder subscribes a picked weekly/monthly on demand (±60 strikes).
- Recorder grids widened to ±60 strikes; SPX 1-minute candles (4 days of history) recorded.
- TASTIER: full 8-panel layout always drawn (empty frames say what they wait for): header
  cards, SPX price + MA9/MA21 + per-bar delta, GEX by strike, cumulative gamma, GEX regime,
  imbalance (CVD), GEX flow top 7, gamma surface, charm surface.
- VS3D: VS3D combined, Book (positions by strike, e-minis per $1, naive calls+/puts−, ATM
  straddle bands, Total/Calls/Puts) and Terrain (gradient) live on naive signing, as vs3dgbt
  showed before its flow seed; GEX³ panel 1 (convention).

## v0.1.4 — 2026-10-18
- Fix: "Fatal streamer error: Your authentication token has expired". The DXLink
  quote token expires after 24 h; the recorder now opens a fresh session every 6 h
  (new access token + new quote token) instead of holding one connection for days,
  and reconnects immediately (no back-off) if a token ever expires anyway.
- Diagnostics show token_refreshes and auto_recovered counts.

## v0.1.3 — 2026-10-17
- Chain snapshots are recorded on weekends and overnight gaps too (every 5 min when the
  market is closed, every 60 s in the trading window), so the next session's chain is
  always on screen and in the recorded history.

## v0.1.2 — 2026-10-17
- Fix: tabs stayed on "Recorder is starting" forever. Each tab and the diagnostics panel
  now re-check the recorder on their own refresh (TASTIER 30 s, AG-REV 15 s, diagnostics 30 s).
- Note: chain snapshots (chain rows) are written only inside the recording window
  (Sun 19:00 ET to Fri 16:20 ET); on a Saturday the count stays 0 by design.

## v0.1.1 — 2026-10-17
- Storage simplified: one repo, one app. Recorded data is saved to the app container's
  disk every 5 min and reloaded after page reloads (vs3dgbt-style day state).
  No GitHub token needed.
- Version shown on every screen and in recorder status for debugging.
- Deploy guide kept outside the repo (it holds the secrets).

## v0.1.0 — 2026-10-17
- App shell: black theme, tabs TASTIER / AG-REV / VS3D, recorder status bar.
- Recorder thread: tastytrade DXLink, SPX 0DTE + 1DTE grids (ATM ±40 strikes),
  TimeAndSale tape with five-bucket classification, quotes, greeks, OI, spot, 60 s chain snapshots.
- TASTIER v0: header cards, GEX by strike, cumulative net gamma, gamma flip, walls.
- AG-REV v0: live classified tape, gate checks (quote-on-print, aggressorSide, spread-leg).
- VS3D: sub-tab bar (port queued).
