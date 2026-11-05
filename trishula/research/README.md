# Tetris research (20 Oct 2026) — not imported by the app

Reverse-engineering AG's "tetris" against the real 16 Oct tape. Scripts read local dumps that are NOT in
this repo (Colab dumps hold API tokens and stay off GitHub): `oct16/` (1-min candles of the expired 16 Oct
chain), `oct16oi/` (Summary OI + daily candles), `today/` (20 Oct dump), `gth/` (19→20 Oct overnight).

Result shipped in core/tetris.py (v0.15.0): weight × greek per strike, each strike scaled to its own peak
(model A = OI×γ, E = OI×vega), colour bands calibrated to AG's colour shares. Ruled out on 16 Oct: global-scale
OI/greek fields, price-grid fields, cumulative flow, prior-day signed baseline + netting, IV-change fields,
cumulative-volume share. Early-warning "specks" (tetris_verify_specks.py) fired 4–10 h before the 11:00 ET
break → not shipped.
