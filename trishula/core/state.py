"""v0.21.2 — state that must survive a reboot / crash, kept in the app's OWN GitHub repo on a side branch.

Today: the VS3D Book's 09:35 lock. Saved once when it forms, read back after a restart, so the Book tab and the
NinjaTrader feed keep the exact 09:35 levels (27 Oct: the 13:2x crash re-locked them at ~14:00 from a thinner book).

  repo    secrets GITHUB_STATE_REPO (default realguru31/TRISHULA)
  token   secrets GITHUB_STATE_TOKEN — fine-grained, this repo only, Contents read/write
  branch  trishula-state (created on first save from the default branch; Streamlit only runs `main`, so a save never
          redeploys the app)
  file    state/lock.json = {"date": "YYYY-MM-DD", "locks": {lock_key: lock}} — overwritten each day, no clean-up.
No token → nothing is saved and the app works as before (the Book header says so). Never raises.
"""
from __future__ import annotations

import base64
import json
import threading
import time

BRANCH = "trishula-state"
PATH = "state/lock.json"
_cfg = {"token": "", "repo": "realguru31/TRISHULA"}
_lock = threading.Lock()
_cache: dict = {}                 # date → {"locks": {...}, "sha": str|None, "at": float}
status: dict = {"configured": False, "loaded": None, "saved": None, "error": None}


def _now() -> str:
    try:
        from .timeutil import now_et
        return now_et().strftime("%H:%M:%S ET")
    except Exception:                               # noqa: BLE001
        return time.strftime("%H:%M:%S")


def configure(token: str, repo: str | None = None) -> None:
    _cfg["token"] = (token or "").strip()
    if repo:
        _cfg["repo"] = repo.strip()
    status["configured"] = bool(_cfg["token"])


def _h():
    return {"Authorization": f"Bearer {_cfg['token']}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}


def _api(method, path, **kw):
    import requests
    return requests.request(method, f"https://api.github.com/repos/{_cfg['repo']}{path}", headers=_h(), timeout=10, **kw)


def _read() -> tuple[dict | None, str | None]:
    r = _api("GET", f"/contents/{PATH}", params={"ref": BRANCH})
    if r.status_code == 404:
        return None, None
    r.raise_for_status()
    j = r.json()
    return json.loads(base64.b64decode(j["content"]).decode()), j.get("sha")


def _ensure_branch() -> None:
    r = _api("GET", f"/git/ref/heads/{BRANCH}")
    if r.status_code == 200:
        return
    info = _api("GET", "")
    info.raise_for_status()
    base = info.json().get("default_branch", "main")
    ref = _api("GET", f"/git/ref/heads/{base}")
    ref.raise_for_status()
    c = _api("POST", "/git/refs", json={"ref": f"refs/heads/{BRANCH}", "sha": ref.json()["object"]["sha"]})
    if c.status_code not in (201, 422):            # 422 = created meanwhile
        c.raise_for_status()


def _day_state(day: str) -> dict:
    """Today's saved locks (one GitHub read per process per day; a failed read retries after 5 min)."""
    with _lock:
        c = _cache.get(day)
        if c is not None and (c.get("ok") or time.time() - c["at"] < 300):
            return c
    c = {"locks": {}, "sha": None, "at": time.time(), "ok": False}
    if _cfg["token"]:
        try:
            j, sha = _read()
            c["sha"] = sha
            if j and j.get("date") == day:
                c["locks"] = dict(j.get("locks") or {})
            c["ok"] = True
            status["loaded"] = f"{_now()} · {len(c['locks'])} lock(s) for {day}"
            status["error"] = None
        except Exception as e:                      # noqa: BLE001
            status["error"] = f"read: {type(e).__name__}: {str(e)[:120]}"
    with _lock:
        _cache[day] = c
    return c


def load_lock(day: str, key: str) -> dict | None:
    if not _cfg["token"]:
        return None
    lk = _day_state(day)["locks"].get(key)
    return dict(lk) if isinstance(lk, dict) else None


def _json_default(o):
    try:
        return float(o)
    except Exception:                               # noqa: BLE001
        return str(o)


def save_lock(day: str, key: str, lk: dict) -> None:
    """Background save (never blocks the page / feed)."""
    if not _cfg["token"]:
        return
    c = _day_state(day)
    with _lock:
        if key in c["locks"] and c["locks"][key].get("ts_ms") == lk.get("ts_ms"):
            return
        c["locks"][key] = {k: v for k, v in lk.items() if k != "src"}
        body = {"date": day, "locks": c["locks"]}

    def _go():
        try:
            _ensure_branch()
            _, sha = _read()
            data = base64.b64encode(json.dumps(body, default=_json_default, indent=1).encode()).decode()
            r = _api("PUT", f"/contents/{PATH}", json={"message": f"lock {day} {key}", "content": data,
                                                       "branch": BRANCH, **({"sha": sha} if sha else {})})
            r.raise_for_status()
            status["saved"] = f"{_now()} · {key} locked {lk.get('locked_at')}"
            status["error"] = None
        except Exception as e:                      # noqa: BLE001
            status["error"] = f"save: {type(e).__name__}: {str(e)[:120]}"
    threading.Thread(target=_go, daemon=True, name="trishula-state").start()
