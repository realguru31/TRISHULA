"""L25 — AG Tetris 21 Oct: target from screenshot + many-way model brute force (multi-expiry, price grid, live IV)."""
import numpy as np, pandas as pd, warnings, itertools
from PIL import Image
from scipy.stats import norm, spearmanr, rankdata
warnings.filterwarnings("ignore")
AG = ["#7a1fa2", "#d36ad6", "#7fd1e8", "#1f4fa8", "#d12b1f", "#f08a24", "#e8cf8a"]
P = np.array([[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in AG], float); Pn = P / P.max(axis=1, keepdims=True)
YEAR = 365 * 86400.0
_t = lambda ms: pd.to_datetime(ms, unit="ms", utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)


def classify(px):
    px = px.reshape(-1, 3).astype(float); mx = px.max(axis=1)
    ok = (mx > 70) & ~(px.min(axis=1) > 200)
    n = px[ok] / mx[ok, None]
    return np.argmin(((n[:, None, :] - Pn[None]) ** 2).sum(-1), axis=1)


def fit_axes(path_px: pd.Series, spot: pd.Series, base_ct: str, x_base: float, pxh_grid, xb_grid):
    """x → time (ET) linear; y = a + b·S + c·x (mild perspective). Returns best (err, x_base, pxh, coef)."""
    best = None
    for xb in xb_grid:
        for pxh in pxh_grid:
            t = pd.Timestamp(base_ct) + pd.Timedelta(hours=1) + pd.to_timedelta((path_px.index.values - xb) / pxh, unit="h")
            ok = (t >= spot.index[0]) & (t <= spot.index[-1])
            if ok.sum() < 150:
                continue
            sv = spot.reindex(pd.DatetimeIndex(t[ok]), method="nearest").values
            y = path_px.values[ok]; x = path_px.index.values[ok].astype(float)
            A = np.c_[np.ones_like(sv), sv, x]
            coef, *_ = np.linalg.lstsq(A, y, rcond=None)
            if coef[1] >= 0:
                continue
            e = np.median(np.abs(y - A @ coef))
            if best is None or e < best[0]:
                best = (e, xb, pxh, coef)
    return best


def target(img, base_ct, xb, pxh, coef, tmin, tmax, kmin, kmax, r=3, step=5):
    im = np.asarray(Image.open(img).convert("RGB"))
    ts = pd.date_range(tmin, tmax, freq=f"{step}min"); ks = np.arange(kmin, kmax + 5, 5)
    T = np.full((len(ks), len(ts)), np.nan)
    t0 = pd.Timestamp(base_ct) + pd.Timedelta(hours=1)
    for j, t in enumerate(ts):
        x = int(round(xb + (t - t0).total_seconds() / 3600 * pxh))
        for i, k in enumerate(ks):
            y = int(round(coef[0] + coef[1] * k + coef[2] * x))
            if not (r <= x < im.shape[1] - r and r <= y < im.shape[0] - r):
                continue
            c = classify(im[y - r:y + r + 1, x - r:x + r + 1])
            if len(c) >= 5:
                T[i, j] = np.bincount(c, minlength=7).argmax()
    return pd.DataFrame(T, index=ks, columns=ts)


def scores(M, T, mask):
    tv = T.values
    g = spearmanr(M[mask], tv[mask]).correlation
    rs = [spearmanr(M[i, mask[i]], tv[i, mask[i]]).correlation for i in range(M.shape[0])
          if mask[i].sum() >= 20 and np.nanstd(tv[i, mask[i]]) > 0 and np.std(M[i, mask[i]]) > 0]
    cs = [spearmanr(M[mask[:, j], j], tv[mask[:, j], j]).correlation for j in range(M.shape[1])
          if mask[:, j].sum() >= 20 and np.nanstd(tv[mask[:, j], j]) > 0 and np.std(M[mask[:, j], j]) > 0]
    return g, (np.nanmean(rs) if rs else np.nan), (np.nanmean(cs) if cs else np.nan)


def greeks(Sgrid, K, T, iv, cp):
    iv = np.where(iv > 0, iv, 0.2); sq = np.sqrt(T)
    d1 = (np.log(Sgrid / K) + 0.5 * iv * iv * T) / (iv * sq); d2 = d1 - iv * sq; pdf = norm.pdf(d1)
    return dict(gamma=pdf / (Sgrid * iv * sq) * Sgrid * Sgrid / 100, vega=Sgrid * pdf * sq / 100,
                avanna=np.abs(pdf * d2 / iv), adelta=np.abs(np.where(cp == 1, norm.cdf(d1), norm.cdf(d1) - 1)),
                charm=np.abs(pdf * (-d2 / (2 * T))), one=np.ones_like(d1))


def norms(M):
    e = 1e-12
    yield "global", M
    yield "log", np.log1p(np.abs(M) / (np.nanmax(np.abs(M)) + e) * 1e4)
    yield "strike_peak", M / (np.nanmax(np.abs(M), axis=1, keepdims=True) + e)
    yield "time_peak", M / (np.nanmax(np.abs(M), axis=0, keepdims=True) + e)
    yield "z_time", (M - M.mean(1, keepdims=True)) / (M.std(1, keepdims=True) + e)
    yield "z_strike", (M - M.mean(0, keepdims=True)) / (M.std(0, keepdims=True) + e)
    yield "rank_time", np.apply_along_axis(rankdata, 0, M)
