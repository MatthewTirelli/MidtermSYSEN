"""
Bar Harbor Traffic Report API: GET /segments and GET /observations.
"""

import pandas as pd

from fastapi import APIRouter, HTTPException

from api.schemas import RoadSegment, TrafficObservation
from api.supabase_client import fetch_road_segments, fetch_traffic_observations

# BPR is applied in this module for GET /observations
import bpr as bpr_module

router = APIRouter()


@router.get("/segments", response_model=list[RoadSegment], summary="List road segments", tags=["segments"])
def get_segments() -> list[RoadSegment]:
    """
    Passthrough to Supabase road_segments table.
    Returns segment geometry, length, road class, lanes, free-flow speed, capacity.
    """
    rows = fetch_road_segments()
    if not rows and _missing_supabase_config():
        raise HTTPException(
            status_code=503,
            detail="SUPABASE_URL and SUPABASE_ANON_KEY must be set",
        )
    return [RoadSegment(**r) for r in rows]


@router.get("/observations", response_model=list[TrafficObservation], summary="List traffic observations with BPR", tags=["observations"])
def get_observations() -> list[TrafficObservation]:
    """
    Traffic observations from Supabase with BPR-derived speed_kmh and travel_time_sec.
    """
    seg_rows = fetch_road_segments()
    obs_rows = fetch_traffic_observations()
    if _missing_supabase_config():
        raise HTTPException(
            status_code=503,
            detail="SUPABASE_URL and SUPABASE_ANON_KEY must be set",
        )
    if not seg_rows:
        return []
    if not obs_rows:
        return []

    segments_df = pd.DataFrame(seg_rows)
    # Normalize column names if needed (Supabase may return snake_case)
    required_seg = {"segment_id", "length_m", "free_flow_speed_kmh", "capacity_vph"}
    if not required_seg.issubset(segments_df.columns):
        raise HTTPException(status_code=500, detail="road_segments missing required columns")
    observations_df = pd.DataFrame(obs_rows)
    observations_df = observations_df[["segment_id", "timestamp", "flow_vph"]].copy()
    with_bpr = bpr_module.apply_bpr(observations_df, segments_df)
    # Ensure timestamp is string for response
    if "timestamp" in with_bpr.columns:
        with_bpr["timestamp"] = with_bpr["timestamp"].astype(str)
    return [TrafficObservation(**r) for r in with_bpr.to_dict(orient="records")]


def _missing_supabase_config() -> bool:
    import os
    return not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_ANON_KEY")
