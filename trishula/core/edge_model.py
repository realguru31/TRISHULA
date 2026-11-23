"""
edge_model.py — expected-loss model for far-OTM SPX puts and calls
====================================================================
One self-contained module: no UI, no orders, no threads, no caching. It does
work only when run_model() is called, and returns a plain result object.

    import edge_model as EM
    run = EM.run_model(toggle="0DTE", spot=7561.67)   # or toggle="1DTE"
    run.put(7220)                    # -> dict: chance reached, expected loss, cautious loss
    run.call(7775)
    run.price("put", 7220, bid=0.60) # same + ratio after fees and cautious ratio
    run.safest("put")                # SAFEST and 2nd SAFEST lines (same rule as the edge scripts)
    run.info                         # what was used: run time, spot, VIX and its date

What the two toggles mean (one trading session of risk in both):
    "0DTE"  sell TODAY's expiry around the OPEN. Risk measured from the spot
            you pass (pre-market / opening spot) to today's low (puts) or
            high (calls). Uses the prior session's closing VIX.
    "1DTE"  sell the NEXT expiry around the CLOSE. Risk measured from the
            spot you pass (today's close) to the next session's low / high.
            Uses the latest VIX.

The numbers have no clock inside the day: the 0DTE figures are right around
the open and the 1DTE figures around the close. Later in the session the
true risk is lower than shown.

Method (tested day by day on real history, each day predicted from earlier
days only): typical move = function of VIX, VIX vs its 22-day average and
the last 5 days' range, recent years weighted more; each past day's move is
divided by the forecast that could have been made before it; those get an
empirical body and a GPD tail whose shape is learned from the data;
expected loss is averaged over every tail the data allows. "Cautious" is the
expected loss at its 95% level. On days that open sharply lower the 0DTE put
figures still run somewhat low.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

HALF_LIFE_YRS = 12        # a day this many years old counts half
TAIL_PCT = 95             # GPD tail above this percentile of the standardized moves
CAUTIOUS_PCT = 95         # "cautious" expected loss = its level at this confidence
REFIT_DAYS = 63           # real-time scale forecasts are refitted this often
FEES_OPEN = 1.77          # $ per contract to sell at tastytrade (1.00 + 0.65 + 0.10 + ~0.02)
OPEN_HISTORY_FROM = "2014-01-01"   # Yahoo's SPX opening prices are real from here on
CLOSE_HISTORY_FROM = "1990-01-01"
XI_GRID = np.linspace(-0.45, 0.49, 48)       # every tail shape with finite variance
TAIL_VIX_GRID = np.linspace(-1.0, 1.0, 21)   # extra VIX power allowed on tail size
FEATURES = ["log_vix", "vix_ma22", "range5"]
MAX_RANGE_PCT = 20.0      # analyse strikes from spot out to 20% away: a 20% fall halts trading for the day


# ── data ───────────────────────────────────────────────────────────────────────
def load_history() -> pd.DataFrame:
    """Daily SPX open/high/low/close and VIX close from Yahoo (same source as the edge scripts)."""
    import yfinance as yf
    end = (dt.datetime.now() + dt.timedelta(days=1)).strftime("%Y-%m-%d")
    spx = yf.download("^GSPC", start="1989-12-01", end=end, progress=False, auto_adjust=False)
    vix = yf.download("^VIX", start="1989-12-01", end=end, progress=False, auto_adjust=False)
    for d in (spx, vix):
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = d.columns.droplevel(1)
    out = spx[["Open", "High", "Low", "Close"]].copy()
    out["vix"] = vix["Close"].reindex(out.index)
    out["vix_open"] = vix["Open"].reindex(out.index)        # v0.48.0: Yahoo's VIX open (03:15 ET overnight value)
    if len(vix) and vix.index[-1] > out.index[-1]:            # premarket: VIX already has today's bar, SPX not yet
        out.attrs["vix_open_today"] = (str(vix.index[-1].date()), float(vix["Open"].iloc[-1]))
    return out


def _now_et() -> dt.datetime:
    from zoneinfo import ZoneInfo
    return dt.datetime.now(ZoneInfo("America/New_York")).replace(tzinfo=None)


# ── the calculation ────────────────────────────────────────────────────────────
def _fit_scale(pos, X, w):
    """Weighted exponential quasi-likelihood for E[move] = exp(X @ theta). Convex: Newton."""
    theta = np.zeros(X.shape[1])
    theta[0] = np.log(np.average(pos, weights=w))
    f = lambda th: np.sum(w * (X @ th + pos * np.exp(-(X @ th))))
    cur = f(theta)
    for _ in range(200):
        r = w * pos * np.exp(-(X @ theta))
        H = (X * r[:, None]).T @ X
        step = np.linalg.solve(H + 1e-9 * np.trace(H) / len(theta) * np.eye(len(theta)), X.T @ (w - r))
        t = 1.0
        while t > 1e-8 and not f(theta - t * step) <= cur:
            t /= 2
        theta = theta - t * step
        new = f(theta)
        if cur - new < 1e-11 * (1 + abs(cur)):
            break
        cur = new
    return theta


def _fit_side(move, X, log_v, w, x_now):
    """Fit one side (moves >0 hurt the seller). Returns f(distance) -> (el, cautious_el, touch), all as fractions of spot."""
    n = len(move)
    pos = np.maximum(move, 0.0)
    theta = _fit_scale(pos, X, w)
    scale_now = float(np.exp(x_now @ theta))

    first = min(1260, n // 3)                      # honest standardized moves: forecast uses earlier days only
    z = np.full(n, np.nan)
    for s in range(first, n, REFIT_DAYS):
        th = _fit_scale(pos[:s], X[:s], w[:s])
        z[s:s + REFIT_DAYS] = move[s:s + REFIT_DAYS] / np.exp(X[s:s + REFIT_DAYS] @ th)
    z, wz, lv = z[first:], w[first:], log_v[first:]
    W = wz.sum()

    order = np.argsort(z)                          # body / tail split (weighted percentile)
    u = float(np.interp(TAIL_PCT / 100.0, (np.cumsum(wz[order]) - 0.5 * wz[order]) / W, z[order]))
    is_tail = z > u
    exceed = z[is_tail] - u
    p_tail = wz[is_tail].sum() / W
    b_order = np.argsort(z[~is_tail])
    body, bw = z[~is_tail][b_order], wz[~is_tail][b_order]
    body_cw = np.concatenate([[0.0], np.cumsum(bw)])
    body_cs = np.concatenate([[0.0], np.cumsum(bw * body)])
    log_r = lv[is_tail]
    ref = log_r.mean()
    log_r = log_r - ref

    beta_grid = exceed.mean() * np.exp(np.linspace(-1.5, 1.5, 101))   # likelihood of every (xi, beta, c)
    ll = np.full((len(XI_GRID), len(beta_grid), len(TAIL_VIX_GRID)), -np.inf)
    for k, c in enumerate(TAIL_VIX_GRID):
        scaled = exceed * np.exp(-c * log_r)
        for i, xi in enumerate(XI_GRID):
            t = 1.0 + xi * scaled[None, :] / beta_grid[:, None]
            ok = (t > 0).all(axis=1)
            ll[i, ok, k] = -len(exceed) * np.log(beta_grid[ok]) - (1.0 + 1.0 / xi) * np.log(t[ok]).sum(axis=1)
    post = np.exp(ll - ll.max())
    I, J, Kc = np.nonzero(post > 1e-7 * post.max())
    wp = post[I, J, Kc] / post[I, J, Kc].sum()
    XI = XI_GRID[I]
    BETA = beta_grid[J] * np.exp(TAIL_VIX_GRID[Kc] * (x_now[1] - ref))   # GPD scale at today's VIX
    mean_excess = BETA / (1.0 - XI)

    def model(distance):
        z_k = distance / scale_now
        d = z_k - u
        if d < 0:                                  # strike inside the body
            i = np.searchsorted(body, z_k, side="right")
            above = body_cw[-1] - body_cw[i]
            vals = ((body_cs[-1] - body_cs[i]) - z_k * above) / W + p_tail * (mean_excess - d)
            touch = p_tail + above / W
        else:
            base = 1.0 + XI * d / BETA             # <= 0 beyond a bounded tail's end
            lb = np.log(np.where(base > 0, base, 1.0))
            vals = p_tail * np.where(base > 0, mean_excess * np.exp((1.0 - 1.0 / XI) * lb), 0.0)
            touch = p_tail * float((wp * np.where(base > 0, np.exp(-lb / XI), 0.0)).sum())
        o = np.argsort(vals)
        hi = vals[o][min(np.searchsorted(np.cumsum(wp[o]), CAUTIOUS_PCT / 100.0), len(o) - 1)]
        return float((wp * vals).sum()) * scale_now, float(hi) * scale_now, float(touch)

    formula = f"VIX^{theta[1]:.2f} x (VIX/avg)^{theta[2]:.2f} x range^{theta[3]:.2f}"
    return model, dict(days=len(z), tail_days=int(is_tail.sum()), formula=formula, xi=float((wp * XI).sum()))


# ── result object ──────────────────────────────────────────────────────────────
class ModelRun:
    """Result of one run. Holds no timers and never recalculates: build a new one to refresh."""

    def __init__(self, info, spot, put_model, call_model, fees_open, safest):
        self.info, self.spot, self.fees_open = info, float(spot), float(fees_open)
        self._m = {"put": put_model, "call": call_model}
        self._safest = safest

    def safest(self, side):
        """[SAFEST, 2nd SAFEST] for "put" or "call": the strike just beyond the biggest and second-biggest
        one-session move since 1990 on days whose VIX close was at or below today's VIX rounded up
        (info["vix_bucket"]). Each: name, strike, move_pct, date (the prior close the move started from).
        Means "has not happened in that history", not "cannot happen"."""
        return self._safest[side]

    def _quote(self, side, strike):
        strike = float(strike)
        dist = (1.0 - strike / self.spot) if side == "put" else (strike / self.spot - 1.0)
        out = {"side": side, "strike": strike, "pct_from_spot": (strike / self.spot - 1.0) * 100.0}
        if dist <= 0:                              # spot is already at or through the strike
            return {**out, "touch": 1.0, "one_in": 1.0, "el_c": float("nan"), "cautious_c": float("nan")}
        el, hi, touch = self._m[side](dist)
        return {**out, "touch": touch, "one_in": (1.0 / touch if touch > 0 else float("inf")),
                "el_c": el * self.spot * 100.0, "cautious_c": hi * self.spot * 100.0}

    def put(self, strike):
        """Chance the strike is reached and expected loss (cents per share) for a short put."""
        return self._quote("put", strike)

    def call(self, strike):
        """Chance the strike is reached and expected loss (cents per share) for a short call."""
        return self._quote("call", strike)

    def display_window(self, side, y_cap_c=50.0, floor_c=0.05, margin_pct=0.5):
        """Strike range worth DRAWING (analysis still covers spot to MAX_RANGE_PCT): from a little inside
        where the expected-loss curve comes down to y_cap_c, out to where it has faded to floor_c."""
        f = lambda d: self._m[side](d)[0] * self.spot * 100.0
        def solve(target):
            lo, hi = 1e-4, MAX_RANGE_PCT / 100.0
            if f(lo) <= target:
                return lo
            if f(hi) >= target:
                return hi
            for _ in range(40):
                mid = 0.5 * (lo + hi)
                lo, hi = (mid, hi) if f(mid) > target else (lo, mid)
            return hi
        near = max(0.0, solve(y_cap_c) - margin_pct / 100.0)
        far = min(MAX_RANGE_PCT / 100.0, solve(floor_c) + margin_pct / 100.0)
        if side == "put":
            return self.spot * (1.0 - far), self.spot * (1.0 - near)
        return self.spot * (1.0 + near), self.spot * (1.0 + far)

    def price(self, side, strike, bid):
        """As put()/call(), plus ratio = (bid - fees) / expected loss and the cautious ratio."""
        q = self._quote(side, strike)
        net = float(bid) * 100.0 - self.fees_open          # $ per contract = cents per share
        q["bid"], q["net_c"] = float(bid), net
        q["ratio"] = net / q["el_c"] if q["el_c"] == q["el_c"] and q["el_c"] > 0 else float("nan")
        q["cautious_ratio"] = net / q["cautious_c"] if q["cautious_c"] == q["cautious_c"] and q["cautious_c"] > 0 else float("nan")
        return q


# ── entry point ────────────────────────────────────────────────────────────────
def run_model(toggle: str = "0DTE", spot: float | None = None, history: pd.DataFrame | None = None,
              now_et: dt.datetime | None = None, fees_open: float = FEES_OPEN, spot_source: str = "",
              vix_mode: str = "close") -> ModelRun:
    """Fit the model now and return a ModelRun.

    toggle   "0DTE" = today's expiry sold around the open; "1DTE" = next expiry sold around the close.
    spot     the level to measure strikes from (required): pre-market / opening spot for 0DTE,
             the closing spot for 1DTE.
    history  optional DataFrame [Open, High, Low, Close, vix] indexed by date; downloaded if omitted.
    now_et   optional naive US/Eastern datetime (defaults to the current ET time).
    vix_mode 0DTE only (v0.48.0): "close" = prior session's closing VIX (default, as before) · "open" = that day's
             Yahoo VIX open (the 03:15 ET overnight value; history fitted the same way) · "max" = the higher of the two.
             Falls back to "close" when today's VIX open is not out yet.
    """
    if toggle not in ("0DTE", "1DTE"):
        raise ValueError("toggle must be '0DTE' or '1DTE'")
    if spot is None or not spot == spot or spot <= 0:
        raise ValueError("spot is required")
    now = now_et or _now_et()
    h = (history if history is not None else load_history()).copy()
    h = h.dropna(subset=["Open", "High", "Low", "Close"])

    log_vix = np.log(h["vix"])
    range_var = np.log(h["High"] / h["Low"]) ** 2 / (4 * np.log(2))
    h["log_vix"] = log_vix
    h["vix_ma22"] = log_vix - log_vix.rolling(22, min_periods=10).mean()
    h["range5"] = np.log(np.sqrt(range_var.rolling(5).mean() * 252) * 100) - log_vix
    h[["vix_ma22", "range5"]] = h[["vix_ma22", "range5"]].replace([np.inf, -np.inf], np.nan).fillna(0.0)

    # Is the newest bar today's unfinished session?
    partial = h.index[-1].date() == now.date() and now.time() < dt.time(16, 15)
    at_open = toggle == "0DTE"
    h["log_vix_close"] = h["log_vix"]
    vix_used = "close"
    h["vix_cut_series"] = h["vix"]                         # SAFEST filter: which VIX each history day is judged by
    if at_open and vix_mode in ("open", "max") and "vix_open" in h:
        lo_next = np.log(h["vix_open"]).shift(-1)          # row t ↔ day t+1's VIX open (the day the move happens)
        today = (h.attrs or {}).get("vix_open_today")
        if not partial and today and today[0] == str(now.date()):
            lo_next.iloc[-1] = np.log(today[1])
        ref_i = -2 if partial else -1
        if np.isfinite(lo_next.iloc[ref_i]):
            L = lo_next if vix_mode == "open" else np.maximum(lo_next, h["log_vix"])
            ma = log_vix.rolling(22, min_periods=10).mean()
            rr = np.log(np.sqrt(range_var.rolling(5).mean() * 252) * 100)
            h["log_vix"] = L
            h["vix_ma22"] = (L - ma).replace([np.inf, -np.inf], np.nan)
            h["range5"] = (rr - L).replace([np.inf, -np.inf], np.nan)
            h["vix_cut_series"] = np.exp(L)                # v0.48.1: SAFEST follows the toggle (next day's VIX open / higher)
            vix_used = vix_mode
    if at_open:      # risk from the open to that day's low / high; inputs = the prior session's close
        put_move = 1.0 - h["Low"].shift(-1) / h["Open"].shift(-1)
        call_move = h["High"].shift(-1) / h["Open"].shift(-1) - 1.0
        start, ref_row = OPEN_HISTORY_FROM, (h.iloc[-2] if partial else h.iloc[-1])
        measure = "from the spot at the open to today's low (puts) / high (calls)"
    else:            # risk from the close to the next session's low / high; inputs = latest
        put_move = 1.0 - h["Low"].shift(-1) / h["Close"]
        call_move = h["High"].shift(-1) / h["Close"] - 1.0
        start, ref_row = CLOSE_HISTORY_FROM, h.iloc[-1]
        measure = "from the spot at the close to the next session's low (puts) / high (calls)"
    if partial:      # the last finished day's outcome is still being made: leave it out of the fit
        put_move.iloc[-2] = np.nan
        call_move.iloc[-2] = np.nan

    tr = h.assign(put_move=put_move, call_move=call_move)
    tr = tr[tr.index >= start].dropna(subset=["put_move", "call_move", "vix"] + FEATURES)
    X = np.column_stack([np.ones(len(tr))] + [tr[f].values for f in FEATURES])
    w = 0.5 ** (((tr.index[-1] - tr.index).days.values / 365.25) / HALF_LIFE_YRS)
    x_now = np.array([1.0, ref_row["log_vix"], ref_row["vix_ma22"], ref_row["range5"]], dtype=float)
    if not np.isfinite(x_now).all():
        raise ValueError("latest VIX / range inputs are missing in the history")

    # SAFEST / 2nd SAFEST, same rule as the edge scripts: biggest close -> next-session moves since 1990
    # among days with VIX <= today's VIX rounded up, applied to the last close (0DTE) or the spot (1DTE).
    if vix_used == "close":
        bucket = int(np.ceil(float(np.exp(ref_row["log_vix_close"]))))     # as before: closing VIX rounded up
    else:                                                  # v0.48.1: exact VIX used today (open / higher of two)
        bucket = round(float(np.exp(ref_row["log_vix"])), 2)
    cl = h[h.index >= CLOSE_HISTORY_FROM]
    fall = cl["Low"].shift(-1) / cl["Close"] - 1.0
    rise = cl["High"].shift(-1) / cl["Close"] - 1.0
    if partial:
        fall.iloc[-2] = rise.iloc[-2] = np.nan
    calm = cl["vix_cut_series"] <= bucket
    base = float(ref_row["Close"]) if at_open else float(spot)
    safest = {
        "put": [{"name": nm, "strike": int((base * (1 + r)) // 5) * 5, "move_pct": r * 100.0, "date": str(d.date())}
                for nm, (d, r) in zip(("SAFEST", "2nd SAFEST"), fall[calm].nsmallest(2).items())],
        "call": [{"name": nm, "strike": int(-((-base * (1 + r)) // 5)) * 5, "move_pct": r * 100.0, "date": str(d.date())}
                 for nm, (d, r) in zip(("SAFEST", "2nd SAFEST"), rise[calm].nlargest(2).items())],
    }

    put_model, put_d = _fit_side(tr["put_move"].values, X, tr["log_vix"].values, w, x_now)
    call_model, call_d = _fit_side(tr["call_move"].values, X, tr["log_vix"].values, w, x_now)
    info = {
        "run_at_et": now.strftime("%Y-%m-%d %H:%M:%S"),
        "toggle": toggle,
        "spot": float(spot),
        "spot_source": spot_source,
        "vix": float(np.exp(ref_row["log_vix"])),
        "vix_date": (str(ref_row.name.date()) if vix_used == "close" else
                     f"{'open' if vix_used == 'open' else 'higher of open / close'} {now.date()}"),
        "vix_mode": vix_used,
        "vix_close": float(np.exp(ref_row["log_vix_close"])),
        "vix_bucket": bucket,
        "vix_cut_kind": {"close": "VIX close", "open": "VIX open", "max": "higher of VIX open / close"}[vix_used],
        "safest_measured_from": base,
        "history_to": str(h.index[-1].date()),
        "measure": measure,
        "put_fit": put_d,
        "call_fit": call_d,
        "fees_open": float(fees_open),
    }
    return ModelRun(info, spot, put_model, call_model, fees_open, safest)