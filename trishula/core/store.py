"""trishula-data repo access through the GitHub contents API.

Writes are small files (parquet parts, json state) every few minutes.
The app repo is never written to: a commit there would redeploy the app.
"""
from __future__ import annotations

import base64
import io
import json

import pandas as pd
import requests

API = "https://api.github.com"


class DataRepo:
    def __init__(self, repo: str, token: str):
        self.repo = repo
        self.h = {"Authorization": f"Bearer {token}",
                  "Accept": "application/vnd.github+json",
                  "X-GitHub-Api-Version": "2022-11-28"}

    def _url(self, path: str) -> str:
        return f"{API}/repos/{self.repo}/contents/{path.lstrip('/')}"

    # ── read ────────────────────────────────────────────────────────
    def ls(self, path: str) -> list[dict]:
        r = requests.get(self._url(path), headers=self.h, timeout=30)
        if r.status_code == 404:
            return []
        r.raise_for_status()
        j = r.json()
        return j if isinstance(j, list) else [j]

    def get(self, path: str) -> bytes | None:
        h = dict(self.h, Accept="application/vnd.github.raw")
        r = requests.get(self._url(path), headers=h, timeout=60)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.content

    def get_json(self, path: str):
        b = self.get(path)
        return json.loads(b) if b else None

    def read_parquet_dir(self, path: str) -> pd.DataFrame:
        parts = [f for f in self.ls(path) if f.get("name", "").endswith(".parquet")]
        frames = []
        for f in sorted(parts, key=lambda x: x["name"]):
            b = self.get(f["path"])
            if b:
                frames.append(pd.read_parquet(io.BytesIO(b)))
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def sessions(self) -> list[str]:
        return sorted((f["name"] for f in self.ls("sessions") if f.get("type") == "dir"),
                      reverse=True)

    # ── write ───────────────────────────────────────────────────────
    def put(self, path: str, data: bytes, message: str) -> None:
        body = {"message": message, "content": base64.b64encode(data).decode()}
        r = requests.get(self._url(path), headers=self.h, timeout=30)
        if r.status_code == 200:                 # overwrite needs the current sha
            body["sha"] = r.json()["sha"]
        r = requests.put(self._url(path), headers=self.h, json=body, timeout=60)
        r.raise_for_status()

    def put_json(self, path: str, obj, message: str) -> None:
        self.put(path, json.dumps(obj, default=str, indent=1).encode(), message)

    def put_parquet(self, path: str, df: pd.DataFrame, message: str) -> None:
        buf = io.BytesIO()
        df.to_parquet(buf, compression="zstd", index=False)
        self.put(path, buf.getvalue(), message)


class LocalRepo(DataRepo):
    """Same interface, files under /tmp on the app container (vs3dgbt-style).
    Survives page reloads and reruns; lost only when the container restarts."""

    def __init__(self, root: str = "/tmp/trishula_data"):
        import os
        self.root = root
        os.makedirs(root, exist_ok=True)

    def _p(self, path: str) -> str:
        import os
        return os.path.join(self.root, path.lstrip("/"))

    def ls(self, path: str) -> list[dict]:
        import os
        d = self._p(path)
        if not os.path.isdir(d):
            return []
        return [{"name": n, "path": f"{path.rstrip('/')}/{n}",
                 "type": "dir" if os.path.isdir(os.path.join(d, n)) else "file"}
                for n in os.listdir(d)]

    def get(self, path: str) -> bytes | None:
        import os
        p = self._p(path)
        if not os.path.isfile(p):
            return None
        with open(p, "rb") as f:
            return f.read()

    def put(self, path: str, data: bytes, message: str = "") -> None:
        import os
        p = self._p(path)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
