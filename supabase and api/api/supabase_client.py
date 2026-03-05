"""
Fetch road_segments and traffic_observations from Supabase REST API.
Uses SUPABASE_URL and SUPABASE_ANON_KEY environment variables.
"""

import os

import httpx


def _get_headers() -> dict[str, str]:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_ANON_KEY", "")
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }


def fetch_road_segments() -> list[dict]:
    """Fetch all rows from road_segments table."""
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not url or not os.environ.get("SUPABASE_ANON_KEY"):
        return []
    full_url = f"{url}/rest/v1/road_segments"
    with httpx.Client() as client:
        r = client.get(full_url, headers=_get_headers())
        r.raise_for_status()
        return r.json()


def fetch_traffic_observations() -> list[dict]:
    """Fetch all rows from traffic_observations table (raw: segment_id, timestamp, flow_vph)."""
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not url or not os.environ.get("SUPABASE_ANON_KEY"):
        return []
    full_url = f"{url}/rest/v1/traffic_observations"
    with httpx.Client() as client:
        r = client.get(full_url, headers=_get_headers())
        r.raise_for_status()
        return r.json()
