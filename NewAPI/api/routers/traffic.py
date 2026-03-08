"""
Traffic API: GET /segments, GET /traffic/window (aggregated per-segment metrics).
"""

import os

from fastapi import APIRouter, HTTPException

from schemas import RoadSegment, TrafficWindowRow
from services.supabase_client import fetch_segments
from services.traffic_service import get_traffic_window

router = APIRouter()


def _missing_supabase_config() -> bool:
    return not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_ANON_KEY")


@router.get(
    "/segments",
    response_model=list[RoadSegment],
    summary="List road segments",
    tags=["segments"],
)
def get_segments() -> list[RoadSegment]:
    """
    Passthrough to Supabase road_segments (served from in-memory cache).
    """
    rows = fetch_segments()
    if not rows and _missing_supabase_config():
        raise HTTPException(
            status_code=503,
            detail="SUPABASE_URL and SUPABASE_ANON_KEY must be set",
        )
    return [RoadSegment(**r) for r in rows]


@router.get(
    "/traffic/window",
    response_model=list[TrafficWindowRow],
    summary="Traffic metrics per segment for a time window",
    tags=["traffic"],
)
def traffic_window(
    date: str,
    start_hour: int,
    end_hour: int,
) -> list[TrafficWindowRow]:
    """
    One row per segment: mean_flow_vph, mean_speed_kmh, mean_travel_time_sec, vc_ratio.
    Example: /traffic/window?date=2025-03-04&start_hour=18&end_hour=19
    """
    if _missing_supabase_config():
        raise HTTPException(
            status_code=503,
            detail="SUPABASE_URL and SUPABASE_ANON_KEY must be set",
        )
    records = get_traffic_window(date=date, start_hour=start_hour, end_hour=end_hour)
    return [TrafficWindowRow(**r) for r in records]
