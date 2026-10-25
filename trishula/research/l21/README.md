# L21 Tetris brute force (20 Oct 2026)

Target: AG's 20 Oct Tetris screenshot (ends 7,761.42), re-gridded to strike × 5-min with
x = time (AG labels are CENTRAL time: 00:50 CT at x=160, 45.4 px/h) and y = 10,860.3 − 1.35·price,
fitted on AG's white price line (median error ≈ 6 points). Colour bands read purple(0) … tan(6).

Scores: overall Spearman (all cells), temporal (per strike, across time), cross-section (per time).
A pure "distance from spot" field already scores 0.73 overall, so the temporal score separates models.

~4,800 candidates: weight {OI, cum vol, OI+cum, cum since 09:30, |net|, net, rolling 15–240 min}
× greek {γ, $γ, vega, |Δ|, vanna, charm, 1} × side {C+P, C−P, C, P} × normalisation
{none, log, per-strike peak, per-time peak, z time, z strike, rank, share, Δ since open}
× per-strike field vs PRICE-GRID field (what the book carries if SPX were at P).

Best: PRICE GRID Σ OI·|vanna(P, K)| (no normalisation) — overall 0.81, temporal 0.38, cross 0.80.
Our shipped model A (per-strike peak OI×γ) scores 0.46 overall. Flow overlays add nothing (temporal 0.38).
Open: AG is asymmetric (warm core above spot after the open, purple below on 16 Oct); ours is symmetric.
