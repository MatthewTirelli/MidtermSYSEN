"""
BPR (Bureau of Public Roads) formula: flow -> speed and travel time.
Used by the Bar Harbor Traffic Report API to compute derived metrics from raw sensor flow.
t = t0 * (1 + alpha * (v/c)^beta); speed_kmh = length_m/1000 / (t_sec/3600).
"""

import numpy as np
import pandas as pd

# Default BPR parameters (match data_pipeline/config.py for consistency)
BPR_ALPHA = 0.15
BPR_BETA = 4.0


def apply_bpr(
    observations: pd.DataFrame,
    segments: pd.DataFrame,
    alpha: float = BPR_ALPHA,
    beta: float = BPR_BETA,
) -> pd.DataFrame:
    """
    BPR: t = t0 * (1 + alpha * (v/c)^beta). Speed = length_m / t_sec, travel_time_sec = t.

    observations must have columns: segment_id, flow_vph (and optionally timestamp).
    segments must have columns: segment_id, length_m, free_flow_speed_kmh, capacity_vph.
    Returns a DataFrame with segment_id, flow_vph, timestamp (if present), speed_kmh, travel_time_sec.
    """
    seg = segments.set_index("segment_id")
    # Free-flow time in seconds: length in km / (speed in km/h converted to km/s)
    t0_sec = (seg["length_m"] / 1000) / (seg["free_flow_speed_kmh"] / 3600)
    cap = seg["capacity_vph"]
    length_m = seg["length_m"]

    out = []
    for _, row in observations.iterrows():
        seg_id = row["segment_id"]
        v = row["flow_vph"]
        c = cap.loc[seg_id]
        t0 = t0_sec.loc[seg_id]
        if c <= 0:
            ratio = 0.0
        else:
            ratio = min(v / c, 3.0)  # cap ratio for numerical stability
        t_sec = t0 * (1 + alpha * (ratio**beta))
        if not np.isfinite(t_sec) or t_sec <= 0:
            speed_kmh = np.nan
            t_sec_out = np.nan
        else:
            speed_kmh = (length_m.loc[seg_id] / 1000) / (t_sec / 3600)
            t_sec_out = t_sec
        rec = {
            "segment_id": seg_id,
            "flow_vph": row["flow_vph"],
            "speed_kmh": round(speed_kmh, 2) if np.isfinite(speed_kmh) else None,
            "travel_time_sec": round(t_sec_out, 2) if np.isfinite(t_sec_out) else None,
        }
        if "timestamp" in row:
            rec["timestamp"] = row["timestamp"]
        out.append(rec)
    return pd.DataFrame(out)
