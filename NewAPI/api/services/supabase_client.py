"""
Supabase REST client: filtered fetches only. Road segments cached at startup.
"""

import os
from typing import Any

import httpx

# In-memory cache for road_segments (static data)
_segments_cache: list[dict[str, Any]] | None = None

# Max rows for segments (single request)
_MAX_WINDOW_ROWS = 50_000
# Page size for observation window pagination
_OBS_PAGE_SIZE = 10_000


def _get_headers() -> dict[str, str]:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_ANON_KEY", "")
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }


def _base_url() -> str:
    return os.environ.get("SUPABASE_URL", "").rstrip("/")


def fetch_segments() -> list[dict[str, Any]]:
    """
    Return road_segments. Uses in-memory cache if already loaded (e.g. at startup).
    Call warm_segment_cache() on app startup; otherwise first call fetches once.
    """
    global _segments_cache
    if _segments_cache is not None:
        return _segments_cache
    url = _base_url()
    if not url or not os.environ.get("SUPABASE_ANON_KEY"):
        return []
    full_url = f"{url}/rest/v1/road_segments"
    headers = {**_get_headers(), "Range": f"0-{_MAX_WINDOW_ROWS - 1}", "Prefer": "count=exact"}
    with httpx.Client() as client:
        r = client.get(full_url, headers=headers)
        r.raise_for_status()
        data = r.json()
    if isinstance(data, list) and data:
        _segments_cache = data
    return _segments_cache or []


def warm_segment_cache() -> None:
    """Load road_segments into memory at application startup."""
    fetch_segments()


def fetch_observations_window(start_iso: str, end_iso: str) -> list[dict[str, Any]]:
    """
    Fetch traffic_observations only for the given time window.
    Uses PostgREST filters: timestamp >= start_iso AND timestamp < end_iso.
    Paginates with _OBS_PAGE_SIZE so the full window is returned.
    """
    base = _base_url()
    if not base or not os.environ.get("SUPABASE_ANON_KEY"):
        return []
    # PostgREST filter: gte = >=, lt = <
    full_url = (
        f"{base}/rest/v1/traffic_observations"
        f"?timestamp=gte.{start_iso}&timestamp=lt.{end_iso}"
    )
    result: list[dict[str, Any]] = []
    start = 0
    with httpx.Client() as client:
        while True:
            end = start + _OBS_PAGE_SIZE - 1
            headers = {
                **_get_headers(),
                "Range": f"{start}-{end}",
                "Prefer": "count=exact",
            }
            r = client.get(full_url, headers=headers)
            r.raise_for_status()
            data = r.json()
            if not isinstance(data, list):
                break
            result.extend(data)
            if len(data) < _OBS_PAGE_SIZE:
                break
            start += _OBS_PAGE_SIZE
    return result
