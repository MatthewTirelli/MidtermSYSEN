"""
Map helpers: WKT parsing, congestion color scale (green → yellow → orange → red).
"""

from __future__ import annotations

from typing import List, Optional

import numpy as np
import pandas as pd

# Bar Harbor, ME
BAR_HARBOR_CENTER_LAT = 44.39
BAR_HARBOR_CENTER_LON = -68.21

# v/c thresholds: Green = free flow, Yellow = moderate, Orange = heavy, Red = severe
VC_FREE = 0.5
VC_MODERATE = 0.7
VC_HEAVY = 0.9
# >= VC_HEAVY = severe


def wkt_to_lonlat_path(wkt_str) -> Optional[List[List[float]]]:
    """Parse WKT LineString/MultiLineString to PathLayer path: list of [lon, lat] pairs."""
    if pd.isna(wkt_str):
        return None
    s = str(wkt_str).strip().upper()
    if not (s.startswith("LINESTRING") or s.startswith("MULTILINESTRING")):
        return None
    try:
        from shapely import wkt as wkt_load
        g = wkt_load.loads(wkt_str)
        if g is None or g.is_empty:
            return None
        if g.geom_type == "LineString":
            xs, ys = g.xy
            return [[float(x), float(y)] for x, y in zip(xs, ys)]
        if g.geom_type == "MultiLineString":
            out = []
            for part in g.geoms:
                xs, ys = part.xy
                out.extend([[float(x), float(y)] for x, y in zip(xs, ys)])
            return out if len(out) >= 2 else None
    except Exception:
        return None
    return None


def vc_to_color(vc: float) -> List[int]:
    """Map v/c ratio to RGB [r,g,b]. Always returns a list of 3 Python ints (0-255) for PyDeck."""
    try:
        if vc is None or (hasattr(vc, "__float__") and pd.isna(vc)):
            return [180, 180, 180]
        x = float(vc)
    except (TypeError, ValueError):
        return [180, 180, 180]
    if x < VC_FREE:
        return [34, 139, 34]   # green (free flow) — list of int 0-255
    if x < VC_MODERATE:
        return [255, 215, 0]   # yellow (moderate)
    if x < VC_HEAVY:
        return [255, 140, 0]   # orange (heavy)
    return [220, 20, 20]      # red (severe)


def vc_severity_label(vc: float) -> str:
    if pd.isna(vc):
        return "No data"
    if vc < VC_FREE:
        return "Free flow"
    if vc < VC_MODERATE:
        return "Moderate"
    if vc < VC_HEAVY:
        return "Heavy"
    return "Severe"


def build_map_data(
    segments: pd.DataFrame,
    seg_stats: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Build segment DataFrame for PyDeck: path, color, tooltip fields.
    seg_stats: optional df with segment_id, mean_speed_kmh, mean_flow_vph, vc_ratio (from observations).
    """
    out = segments.copy()
    if "geometry_wkt" not in out.columns:
        out["path"] = np.nan
    else:
        out["path"] = out["geometry_wkt"].map(wkt_to_lonlat_path)
    out = out[out["path"].notna()].copy()
    out["color"] = [[180, 180, 180]] * len(out)
    out["street_name"] = out.get("street_name", pd.Series([""] * len(out))).fillna("").astype(str)
    out["road_class"] = out.get("road_class", pd.Series([""] * len(out))).fillna("").astype(str)
    # Do not add vc_ratio/mean_flow_vph/mean_speed_kmh here so merge brings single columns (no _x/_y)
    if seg_stats is not None and not seg_stats.empty:
        cols = ["segment_id", "mean_speed_kmh", "mean_flow_vph", "vc_ratio"]
        merge_df = seg_stats[[c for c in cols if c in seg_stats.columns]]
        out = out.merge(merge_df, on="segment_id", how="left")
        if "vc_ratio" in out.columns:
            out["color"] = out["vc_ratio"].map(lambda v: vc_to_color(v))
    else:
        out["vc_ratio"] = np.nan
        out["mean_flow_vph"] = np.nan
        out["mean_speed_kmh"] = np.nan
    return out
