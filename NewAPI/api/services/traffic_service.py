"""
Traffic service: window-only fetch, vectorized BPR, aggregation by segment.
Powers GET /traffic/window. No pagination loops; DB filter + in-memory aggregate.
"""

from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from bpr import apply_bpr_vectorized
from services.supabase_client import fetch_observations_window, fetch_segments

REQUIRED_SEG = {"segment_id", "length_m", "free_flow_speed_kmh", "capacity_vph"}
REQUIRED_OBS = {"segment_id", "timestamp", "flow_vph"}


def _window_to_iso(date: str, start_hour: int, end_hour: int) -> tuple[str, str] | None:
    """Return (start_iso, end_iso) for the time window. None if invalid."""
    if not (0 <= start_hour <= 23 and 0 <= end_hour <= 23):
        return None
    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return None
    start_dt = dt.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    end_dt = dt.replace(hour=end_hour, minute=0, second=0, microsecond=0)
    if end_hour <= start_hour:
        end_dt += timedelta(days=1)
    return start_dt.strftime("%Y-%m-%dT%H:%M:%S"), end_dt.strftime("%Y-%m-%dT%H:%M:%S")


def get_traffic_window(
    date: str,
    start_hour: int,
    end_hour: int,
) -> list[dict[str, Any]]:
    """
    One row per segment for the time window: mean_flow_vph, mean_speed_kmh,
    mean_travel_time_sec, vc_ratio. Uses DB filtering and vectorized BPR.
    """
    window = _window_to_iso(date, start_hour, end_hour)
    if not window:
        return []
    start_iso, end_iso = window

    seg_rows = fetch_segments()
    if not seg_rows:
        return []
    seg_df = pd.DataFrame(seg_rows)
    if not REQUIRED_SEG.issubset(seg_df.columns):
        return []
    seg_df = seg_df[list(REQUIRED_SEG)].drop_duplicates(subset=["segment_id"])

    obs_rows = fetch_observations_window(start_iso, end_iso)
    if not obs_rows:
        return []
    obs_df = pd.DataFrame(obs_rows)
    if not REQUIRED_OBS.issubset(obs_df.columns):
        return []
    obs_df = obs_df[["segment_id", "timestamp", "flow_vph"]].copy()

    # Segment index per observation via merge (no Python loop)
    seg_df = seg_df.assign(seg_idx=np.arange(len(seg_df)))
    obs_with_idx = obs_df.merge(
        seg_df[["segment_id", "seg_idx"]],
        on="segment_id",
        how="inner",
    )
    seg_idx = obs_with_idx["seg_idx"].values.astype(np.int64)
    flow_arr = obs_with_idx["flow_vph"].astype(float).values

    length_m = seg_df["length_m"].astype(float).values
    free_flow_speed_kmh = seg_df["free_flow_speed_kmh"].astype(float).values
    capacity_vph = seg_df["capacity_vph"].astype(float).values

    speed_kmh, travel_time_sec = apply_bpr_vectorized(
        seg_idx,
        flow_arr,
        length_m,
        free_flow_speed_kmh,
        capacity_vph,
    )

    obs_with_idx = obs_with_idx.assign(speed_kmh=speed_kmh, travel_time_sec=travel_time_sec)

    # Aggregate by segment_id (no Python loops)
    agg = obs_with_idx.groupby("segment_id", as_index=False).agg(
        mean_flow_vph=("flow_vph", "mean"),
        mean_speed_kmh=("speed_kmh", "mean"),
        mean_travel_time_sec=("travel_time_sec", "mean"),
    )
    cap_series = seg_df.set_index("segment_id")["capacity_vph"]
    agg = agg.join(cap_series, on="segment_id", how="left")
    cap = agg["capacity_vph"].astype(float)
    mean_flow = agg["mean_flow_vph"].astype(float)
    vc = np.where(
        (cap > 0) & np.isfinite(cap),
        np.clip(mean_flow / cap, 0.0, 3.0),
        np.nan,
    )
    agg["vc_ratio"] = pd.Series(np.where(np.isfinite(vc), np.round(vc, 4), np.nan)).replace({np.nan: None})
    agg["mean_speed_kmh"] = agg["mean_speed_kmh"].replace({np.nan: None})
    agg["mean_travel_time_sec"] = agg["mean_travel_time_sec"].replace({np.nan: None})
    agg = agg.drop(columns=["capacity_vph"], errors="ignore")

    return agg.to_dict(orient="records")
