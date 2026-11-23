"""HTTP with retries. Default library User-Agent; a generic descriptive UA (no personal details) only
where a source requires one (SEC). FRED drops requests carrying unknown custom UAs."""
from __future__ import annotations

import time

import requests

UA = "macro-liquidity-model/0.1 (research use)"


def get(url: str, params: dict | None = None, headers: dict | None = None, retries: int = 3,
        timeout: int = 45, descriptive_ua: bool = False) -> requests.Response:
    h = {"User-Agent": UA} if descriptive_ua else {}
    h.update(headers or {})
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=h, timeout=timeout)
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
            r.raise_for_status()
            return r
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
            last = e
            resp = getattr(e, "response", None)
            if resp is not None and resp.status_code not in (429, 500, 502, 503, 504):
                break
            time.sleep(2 ** attempt)
    raise RuntimeError(f"GET {url} failed: {last}")
