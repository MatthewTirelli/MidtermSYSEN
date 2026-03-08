"""
BPR (Bureau of Public Roads): flow -> speed and travel time.
Vectorized numpy implementation for performance (no row-by-row loops).
"""

import numpy as np

BPR_ALPHA = 0.15
BPR_BETA = 4.0


def apply_bpr_vectorized(
    seg_idx: np.ndarray,
    flow_vph: np.ndarray,
    length_m: np.ndarray,
    free_flow_speed_kmh: np.ndarray,
    capacity_vph: np.ndarray,
    alpha: float = BPR_ALPHA,
    beta: float = BPR_BETA,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Vectorized BPR: t = t0 * (1 + alpha * (v/c)^beta); speed = length_km / (t_sec/3600).

    seg_idx: 1d int array of segment index per observation (from merge/map).
    flow_vph: 1d array. length_m, free_flow_speed_kmh, capacity_vph: 1d per segment.

    Returns (speed_kmh, travel_time_sec) as 1d arrays (same length as flow_vph).
    """
    valid = (seg_idx >= 0) & (seg_idx < len(length_m))
    length = np.where(valid, np.take(length_m, seg_idx), np.nan)
    cap = np.where(valid, np.take(capacity_vph, seg_idx), np.nan)
    ff_speed = np.where(valid, np.take(free_flow_speed_kmh, seg_idx), np.nan)

    t0_sec = (length / 1000.0) / (ff_speed / 3600.0)
    ratio = np.where(
        (cap > 0) & np.isfinite(cap),
        np.clip(flow_vph / cap, 0.0, 3.0),
        np.nan,
    )
    t_sec = t0_sec * (1 + alpha * (ratio**beta))
    speed_kmh = np.where(
        np.isfinite(t_sec) & (t_sec > 0),
        (length / 1000.0) / (t_sec / 3600.0),
        np.nan,
    )
    return speed_kmh, t_sec
