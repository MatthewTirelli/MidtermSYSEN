"""
Fetch road_segments and traffic_observations from Supabase REST API.
Uses SUPABASE_URL and SUPABASE_ANON_KEY environment variables.
PostgREST returns at most 1000 rows per request by default; we paginate to get all rows.
"""

import os

import httpx

# Chunk size for Supabase REST pagination (PostgREST default max is 1000)
_PAGE_SIZE = 1000


def _get_headers() -> dict[str, str]:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_ANON_KEY", "")
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }


def _fetch_all_pages(client: httpx.Client, full_url: str, headers: dict[str, str]) -> list[dict]:
    """Paginate with Range header to get every row (avoids PostgREST 1000-row default limit)."""
    out: list[dict] = []
    start = 0
    # Optional: ask for exact count in Content-Range (e.g. "0-999/2321")
    range_headers_base = {**headers, "Range-Unit": "items", "Prefer": "count=exact"}
    while True:
        end = start + _PAGE_SIZE - 1
        range_headers = {**range_headers_base, "Range": f"{start}-{end}"}
        r = client.get(full_url, headers=range_headers)
        r.raise_for_status()
        page = r.json()
        if not page:
            break
        out.extend(page)
        # Content-Range e.g. "0-999/2321" when Prefer: count=exact
        content_range = r.headers.get("Content-Range", "")
        if "/" in content_range:
            total_str = content_range.split("/")[-1].strip()
            if total_str != "*" and total_str.isdigit():
                total = int(total_str)
                if len(out) >= total:
                    break
        if len(page) < _PAGE_SIZE:
            break
        start += _PAGE_SIZE
    return out


def fetch_road_segments() -> list[dict]:
    """Fetch all rows from road_segments table (paginates past PostgREST 1000-row limit)."""
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not url or not os.environ.get("SUPABASE_ANON_KEY"):
        return []
    full_url = f"{url}/rest/v1/road_segments"
    with httpx.Client() as client:
        return _fetch_all_pages(client, full_url, _get_headers())


def fetch_traffic_observations() -> list[dict]:
    """Fetch all rows from traffic_observations table (paginates past PostgREST 1000-row limit)."""
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not url or not os.environ.get("SUPABASE_ANON_KEY"):
        return []
    full_url = f"{url}/rest/v1/traffic_observations"
    with httpx.Client() as client:
        return _fetch_all_pages(client, full_url, _get_headers())
