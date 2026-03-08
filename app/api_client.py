"""
Cached API client for Bar Harbor Traffic Report API.
GET /segments and GET /observations.
Returns (df, error, status_code, num_records).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

import httpx
import pandas as pd

_api_cache: dict[str, tuple[Any, Optional[str]]] = {}
HTTP_TIMEOUT = 300.0


def _cache_key(path: str, params: Optional[dict] = None) -> str:
    raw = path + json.dumps(params or {}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def fetch_segments(base_url: str) -> tuple[Optional[pd.DataFrame], Optional[str], Optional[int], Optional[int]]:
    url = f"{base_url.rstrip('/')}/segments"
    key = _cache_key("segments", None)
    if key in _api_cache:
        d, err = _api_cache[key]
        return d, err, 200 if d is not None else None, len(d) if d is not None and isinstance(d, pd.DataFrame) else None
    try:
        r = httpx.get(url, timeout=HTTP_TIMEOUT)
        status_code = r.status_code
        r.raise_for_status()
        data = r.json()
        if not data:
            return None, "No data from /segments", status_code, 0
        df = pd.DataFrame(data)
        _api_cache[key] = (df, None)
        return df, None, status_code, len(df)
    except httpx.HTTPStatusError as e:
        return None, str(e), (e.response.status_code if e.response else None), None
    except Exception as e:
        return None, str(e), None, None


def fetch_observations(
    base_url: str,
    *,
    limit: int = 10_000,
    date: Optional[str] = None,
    start_hour: Optional[int] = None,
    end_hour: Optional[int] = None,
) -> tuple[Optional[pd.DataFrame], Optional[str], Optional[int], Optional[int]]:
    params = {"limit": int(limit)}
    if date:
        params["date"] = str(date).strip()
    if start_hour is not None:
        params["start_hour"] = int(start_hour)
    if end_hour is not None:
        params["end_hour"] = int(end_hour)
    key = _cache_key("observations", params)
    if key in _api_cache:
        d, err = _api_cache[key]
        return d, err, 200 if d is not None else None, len(d) if d is not None and isinstance(d, pd.DataFrame) else None
    url = f"{base_url.rstrip('/')}/observations"
    try:
        r = httpx.get(url, params=params, timeout=HTTP_TIMEOUT)
        status_code = r.status_code
        r.raise_for_status()
        data = r.json()
        if not data:
            return None, "No data from /observations", status_code, 0
        df = pd.DataFrame(data)
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=False)
        _api_cache[key] = (df, None)
        return df, None, status_code, len(df)
    except httpx.HTTPStatusError as e:
        return None, str(e), (e.response.status_code if e.response else None), None
    except Exception as e:
        return None, str(e), None, None
