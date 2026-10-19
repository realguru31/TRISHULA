# TRISHULA — build queue & handover (as of 2026-10-18)

Latest build: **v0.10.2** (all approved releases done; deployed version = whatever the user last uploaded) (GitHub repo `realguru31/trishula`, main module `trishula/app.py`, Streamlit Cloud, Python 3.12, secrets TT_CLIENT_SECRET / TT_REFRESH_TOKEN in Streamlit only).
Rules: build ONLY on user's "APPROVE" (caps). Semantic versioning in core/version.py + CHANGELOG.md, version visible on every screen. Colab test scripts always ship with both tastytrade tokens filled in. After every upload: Streamlit → ⋮ → Reboot app (recorder is a cached background thread).
Reference source: `vs3dgbt_0.9.79.py` in this project (port target for VS3D).

## Proven tastytrade facts (Colab 2026-10-17/18)
- DXLink Greeks/Quote/Summary/Trade on SPXW legs: OK. Spot from Trade (SPX quote bid/ask is junk).
- TimeAndSale replay via `fromTime`: WORKS on weekends. Every print has bid/ask at print, aggressorSide BUY/SELL (100% filled), spreadLeg (~42% true).
- Replay cap: **last 1,000 prints per contract** (busy ATM legs reach back only to ~10:30–13:00 Friday). ~4,600 prints/s; 60 contracts in 10 s. eventFlags: 0x01 TX_PENDING, 0x02 REMOVE_EVENT, 0x04 SNAPSHOT_BEGIN, 0x08 SNAPSHOT_END, 0x10 SNIP — completion detected by quiet time.
- Candle {=5m} carries bidVolume/askVolume (signed volume, uncapped, full session). {=1d} does not.
- DXLink quote token expires 24 h → recorder reconnects every 6 h (v0.1.4).
- Limits: 5 sessions, 25,000 subs/session, 100 Candle subs, 10,000 sub changes/min.

## User decisions (2026-10-18)
- Book opens FLOW-SIGNED (toggle clean / net flow / naive).
- Seed window: prior RTH + overnight for the expiry.
- MID prints: signed by aggressorSide (differs from GBT/vs3dgbt — caption it).
- Seed: re-fetched from tastytrade every start (no persistence).
- VS3D ports (Book, Terrain, combined, GEX³) in MATPLOTLIB (vs3dgbt code as-is, data inputs swapped). TASTIER + AG-REV stay Plotly.
- One APPROVE covers all releases v0.2.1 → v0.6.0, built in order, one zip per release.

## Progress tracker (updated after every release)
| Release | Status | Zip | Notes |
| --- | --- | --- | --- |
| v0.1.0–v0.1.4 | DONE | — | shell, recorder, tab refresh, weekend snapshots, 6 h token refresh |
| v0.2.0 | DONE · deployed | trishula-v0.2.0.zip | control bar, TASTIER 8 panels, naive VS3D |
| v0.2.1 | DONE | trishula-v0.2.1.zip | fixes + tab styling |
| v0.3.0 | DONE | trishula-v0.3.0.zip | TAS fromTime seed+backfill, 5m candle fill, dsign, Book flow lens (Plotly interim), AG-REV CVD |
| v0.4.0 | DONE | trishula-v0.4.0.zip | Book + combined + playback |
| v0.5.0 | DONE | trishula-v0.5.0.zip | Terrain |
| v0.6.0 | DONE | trishula-v0.6.0.zip | GEX³ |
| v0.7.0 | DONE | trishula-v0.7.0.zip | R1 refresh · R2 universal replay · R3 Book layout · R4 image scaling |
| v0.8.0 | DONE | (in v0.9.0 zip) | VS3D Interval · Market Read · DT |
| v0.9.0 | DONE | trishula-v0.9.0.zip | AG-REV signals Q1–Q5/W + V1–V5 (SPXFlow v2.10) · TASTIER Velocity/Absorb/Pressure · VRVP |
| v0.10.0 | DONE | trishula-v0.10.0.zip | GTH session on all tabs · spike filter (robust z + cross-section + floor, GTH/RTH baselines) · 3-D AG-REV ridges/surface |
| v0.10.1 | DONE | trishula-v0.10.1.zip | spike filter tuned on real tape (per-session defaults, single-leg, package merge) |
| v0.10.2 | DONE | trishula-v0.10.2.zip | stale-SPX-at-connect fix · /ES overnight price backfill · VIX from 03:15 |

## Queue (staged releases)
### v0.2.1 — fixes + look (small)
- 0  Expiry bar re-runs once recorder is ready (no stuck "loading…")
- 0b Status line: "recording 0DTE 10/19 · 1DTE 10/20 (seed)"
- 0c Weekly/Monthly "loading…" label + tab refresh until data arrives → "ready ✓"
- 1  Version-mismatch guard (new code vs running recorder → auto-restart or red "Reboot app" banner)
- 2  Silence "Task was destroyed / aclose()" shutdown noise
- 12 Tab styling: bordered tabs, faint dividers, active tab blue top border, hover, top-level larger than sub-tabs
### v0.3.0 — signed data foundation
- 4  Seed: Candle 5m bid/ask volume = net/total per contract (full session) + replayed prints (last 1,000) for spread-leg/clean-B, premium, CVD; SNAPSHOT_END check; batches of 100 candle subs
- 5  Gap backfill after restart/disconnect (replay; candles beyond cap)
- 6  Per-strike seed coverage on screen (prints-from time, candle coverage)
- 7  AG-REV + TASTIER CVD from seed
### v0.4.0 — VS3D Book + combined (port of vs3dgbt book_figure / signed_book_rows / _render_book)
- 8  Book: lenses flow-signed (green/red, sign×OI contracts, full mass, opacity=conf, unseeded naive faded at 0.2) · clean-signed (blue/magenta, single-leg only, no verdict=no bar) · net flow participant view (blue/yellow); controls Bars MM/naive, Show Total/Calls/Puts, zoom ±/full, comparison open dots, exhausted-extent sticks, 1× straddle, Δ ladder + ⚡ divergence, spot-path overlay with session time axis, card levels BALANCE/UP/DN with de-collision, 10-pt price ticks, KEY LEVELS card, THE STRIP, seed badge
- 11 VS3D combined (Book×spot 1.0 | Gamma+Charm terrain 1.5, bottoms aligned) + global controls: expiries to aggregate 1–5, price window ±%, live price layer 15/30/60/off, snapshot scrubber, playback ⏮▶⏸⏹ 1/2/4 s
### v0.5.0 — Terrain port (terrain_grid / scale / intensity / pockets / contours)
- 10 Forward-projected field 170 price × 84 time (09:30–16:00), BS greek at hypothetical spot/τ; Greek Delta Change/Gamma/Charm/|Γ|/Decay; field mode Aggregate/Per-strike; weighting OI+Vol/OI/Vol/legacy; range Manual cap (Calibrate/Reset, autopilot 1.5×/0.4×)/Percentile/StdDev; intensity Power 0.40/Sqrt/Arcsinh; opacity 0.38; saturation; smoothing 0.25; zoom; contours zero+ridges; negative-γ pockets top-N; straddle bounds; Pinak overlay; vol adj; simulated gamma/charm; stacked charm panel with charm flip; dsign drives field when signed
### v0.6.0 — GEX³ port (gex3_lens_rows / gex3_draw_profile / gex3_zone_shade / gex3_model / _render_gex3)
- 9  3 stacked panels (CONVENTION naive · FLOW-SIGNED · ΔOI overnight or live volume w/ dotted P2), candles across RTH, right-anchored density (buy green / sell red fills+lines, TOTAL orange, |net| white, ▲▼ peaks, HHI◆ top-5), γ fields, levels flip/CW/PW/PIN/CEIL/FLOOR/UHW/DHW with de-collided labels, scorecard, γ dial, colour readout + model-detail expander; sliders ±% room 0.5, density width 0.45, panel height 5.5; y auto-fit
### Later (needs recorded RTH / user input)
- Velocity/Absorb/Pressure overlays (definitions needed) · VRVP (SPY volume) · VS3D Interval, Market Read, DT · AG-REV signals Q1–Q5/W/B + V1–V5 panels

## Queued → APPROVED 2026-10-18 (R1–R4 built in v0.7.0)
- R2 Universal replay player (user 2026-10-18), placed ABOVE the three main tabs next to R1. Controls (final, user 2026-10-18): time scrubber · ⏮ first frame · ▶ play · ⏸ pause · ⏹ stop with a small 'LIVE' label next to it · speed 1 / 2 / 3 s per frame. No separate LIVE/Replay toggle — modes are implicit:
    · ⏸ while live = freeze at the latest frame → player mode (all tabs frozen there)
    · ▶ = advance one frame per 1/2/3 s from the current frame (from live: starts at first frame)
    · ⏮ = jump to first frame, paused (player mode) · dragging the scrubber = player mode at that frame
    · ⏹ LIVE = leave player mode, resume live data + refresh timer
    · A visible badge shows the mode: 🔴 LIVE or ⏸/▶ REPLAY hh:mm. Every tab (TASTIER, AG-REV, VS3D and its sub-tabs) renders "as of" the selected time: chain snapshot at t, prints ≤ t, candles/spot ≤ t, dsign as of t. Moves the existing player out of VS3D controls (where it lives today, collapsed).
- R3 Book tab layout (user 2026-10-18, screenshot: too much white space). Proposal:
    · Charts side by side, shared price axis: [1] FLOW-SIGNED (MM-inferred) · [2] CLEAN-B (single-leg tape) — both always on by default · [3] selectable third chart: Net flow / Naive / none.
    · REMOVE: Total/Calls/Puts radio (net view only), Bars MM/Naive radio and Book-signing radio (replaced by the fixed pair + third-chart selector).
    · KEEP (one compact row): zoom ➕➖↔ (grouped together, not spread across the page), comparison dots, 1× straddle, Δ ladder, spot path, card, strip.
    · KEY LEVELS card + STRIP sit beside the charts / above in a tight row instead of stacked with empty space.
    · Open: spot path on all charts or chart 1 only; card/strip always on or toggles.
- R4 Image sizing (user 2026-10-18): terrain/charm look right at normal browser zoom; gaps only appeared zoomed out (images stop at their pixel size). Book is the real problem: one huge tall chart (11×12 in) under a small card with empty space → fixed by R3 (charts side by side, height capped to fit the screen, card+strip in a tight row). Minor: let images scale with zoom.
- R1 Refresh interval control (user 2026-10-18): universal bar above the tabs (with R2), default 5 min, slider 1–10 min in 1-min steps.
  Scope DECIDED (user 2026-10-18): screen refresh only, for all tabs (replaces the VS3D 15/30/60 s live layer). Chain snapshots stay every 60 s, so replay/terrain/09:35 lock keep full detail.

## Status after v0.6.0 (2026-10-18)
- All approved releases are built: v0.2.1 → v0.6.0. Upload the latest zip only, then Reboot app.
- Verify live on Monday's RTH session:
  - seed replay + candle fill counts in the status bar
  - Book dots/bars
  - 09:35 lock
  - THE STRIP VIX chip
  - terrain candles
  - GEX³ panel 3 (ΔOI needs one overnight recorded first; falls back to volume)
- Known limits:
  - /tmp data (LocalRepo) is lost on redeploy, so ΔOI history and flushed sessions reset.
  - Replayed prints get a 1m-candle spot and no greeks; TASTIER CVD uses the current delta
    as a stand-in.
- Next (needs user input before APPROVE): Velocity/Absorb/Pressure definitions · VRVP (SPY) ·
  Interval · Market Read · DT · AG-REV signals Q1–Q5/W/B + V1–V5.

## Status 2026-10-19 (before Monday open)
- Everything queued is built (R1–R4 in v0.7.0; Interval/Read/DT; AG-REV signals from SPXFlow_v2.10.xlsm; TASTIER overlays). Upload trishula-v0.9.0 only, then Reboot app.
- "B" signal: not in SPXFlow v2.10 — nothing built. Velocity/Absorb/Pressure/VRVP formulas are TRISHULA definitions (see core/overlays.py docstring) — user to review.
- Next: watch the live session, then tune (ZThresh/MinPrem defaults are the workbook's).

## Status 2026-10-19 02:30 ET
- v0.10.0 built (GTH, spike filter, 3-D AG-REV). Tested on fake data only.
- Waiting on user's Colab real-data dump (trishula_sample_dump.py → trishula_sample.zip) to validate overnight prints arrive and to tune the spike filter on real tape.

## Real-data facts (Colab dump 2026-10-19 02:31 ET)
- Overnight SPXW prints stream via DXLink: 27.8k Sun 20:15→Mon 02:31, ~200/90 s live, median 1 lot, bid/ask on 100 %, aggressorSide 99.9 %.
- SPX/SPY 1m candles: RTH only (+16:00–16:20 for SPX). VIX 5m from 03:15. Overnight spot must be synthetic parity.
- eventFlags seen: 0, 1 (TX_PENDING), 4 (SNAPSHOT_BEGIN), 5. spreadLeg share 46 % (32 % overnight).
- Contract-minute volume Fri RTH: median 3, p99 159, p99.9 1,501. Overnight: median 2, p99 48.
- Open observation: Q5 can fire often in slow overnight drifts (workbook rule, 5-min cooldown) — watch live.

## Watch list after Mon 19 Oct RTH (decide with user)
- Q5 noise in slow overnight drifts → min price move / longer GTH cooldown?
- RTH spike count (defaults aim ~10–15/day).
- Session end 16:00 → 16:15 (non-expiring SPXW trades to 16:15; ~10k prints Fri).
- 19 Oct 14:37 crash = out of memory (per-print plotly charts) → fixed v0.11.1; watch 'mem' in the status bar on the next full day.
- Known limit: reboot/redeploy wipes the day's in-memory history (no external storage by user choice).
- "B" signal: not in SPXFlow v2.10 — needs a definition.

## Built in v0.11.0 (APPROVE 09:17): L1, L3, L4, L5 · still queued: L2

## Queued (user 2026-10-19 04:37)
- L1 Loading indicator: screens stay blank then appear all at once. Add a visible progress bar per tab/sub-tab while it computes
  (st.progress stepping through stages, e.g. "loading chain → signs → book → card → terrain → render", with % and stage label),
  plus a thin top-of-page bar during full-page refresh / replay steps. Also show placeholder frames immediately so layout doesn't jump.
- L2 GTH toggle per viewer: core/session.STATE is process-wide (shortcut) — two browsers with different settings flip it for each other. Move to st.session_state / pass session mode explicitly through bars_for/session_date/axes.
- L3 Interval: wasted space — y-axis spans ~7380–7930 while activity sits 7600–7740. Auto-fit y to top-N strikes + price path (vs3dgbt _intv_ylim) with small pad; x-axis end at "now" + margin instead of empty future to 16:00 (toggle).
- L4 DT legend on the chart + caption (user's 08-27 glyph grammar): blue = bullish, magenta = bearish; FILLED = extending (long building / fresh paper), HOLLOW = receding (short covering / long unwinding); near-zero dot (< floor) = fresh paper, always filled. Also: DT counts only from 09:30 — option to run from 20:15 when GTH is on.
- L5 Book layout (user 06:38): charts too tiny, card too wide. Card on TOP (full width, compact), remove "⬇ card" download button.
  Below: chart 1 (MM-inferred) + chart 2 (clean-B single-leg) side by side at half width each as default. Third chart only when a
  lens is picked in the selectbox → then all three across the full width. Spot path on ALL charts (twin time axis, like chart 1),
  checkbox renamed "Spot path".
