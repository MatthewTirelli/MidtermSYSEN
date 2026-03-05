"""
7-step pipeline: OSM road network -> road_segments.csv + traffic_observations.csv
for Supabase upload. Follows .cursor/rules/csv-supabase-data-strategy.mdc
and resolves gaps from the strategy analysis (time resolution, BPR, geometry, IDs, capacity).
"""

import os
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import re

# Optional: use osmnx if available for real OSM data
try:
    import osmnx as ox
    import geopandas as gpd
    from shapely import wkt
    from shapely.geometry import LineString
    HAS_OSMNX = True
except ImportError:
    HAS_OSMNX = False

from config import (
    OSM_PLACE,
    LOCAL_OSM_FILE,
    OSM_NETWORK_TYPE,
    TIME_RESOLUTION_HOURS,
    TIME_RANGE_DAYS,
    BPR_ALPHA,
    BPR_BETA,
    RANDOM_SEED,
    CAPACITY_VPH_PER_LANE,
    DEFAULT_SPEED_KMH,
    BASELINE_VPH_PER_LANE,
    OUTPUT_ROAD_SEGMENTS_CSV,
    OUTPUT_TRAFFIC_OBSERVATIONS_CSV,
)


# --- Step 1: Extract road network from OSM (or demo segments) ---
def extract_road_network(place: str, local_osm_path: str = None):
    """Load street network from a local OSM file (if path exists) or download from OpenStreetMap; return edges as GeoDataFrame."""
    if not HAS_OSMNX:
        raise ImportError("osmnx and geopandas are required for OSM extraction. Install with: pip install osmnx geopandas")
    # Resolve path relative to project root (parent of data_pipeline)
    if local_osm_path:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(base_dir)
        full_path = os.path.join(project_root, local_osm_path)
        if os.path.isfile(full_path):
            # .osm is XML; graph_from_xml does not take network_type (file content defines the graph)
            G = ox.graph_from_xml(full_path, retain_all=True)
            # Ensure edge lengths are available in meters for downstream calculations
            try:
                if hasattr(ox, "distance") and hasattr(ox.distance, "add_edge_lengths"):
                    G = ox.distance.add_edge_lengths(G)
                elif hasattr(ox, "add_edge_lengths"):
                    G = ox.add_edge_lengths(G)  # older API
            except Exception:
                pass
            gdf_edges = ox.graph_to_gdfs(G, nodes=False)
            return gdf_edges.reset_index()
    G = ox.graph_from_place(place, network_type="drive")
    try:
        if hasattr(ox, "distance") and hasattr(ox.distance, "add_edge_lengths"):
            G = ox.distance.add_edge_lengths(G)
        elif hasattr(ox, "add_edge_lengths"):
            G = ox.add_edge_lengths(G)
    except Exception:
        pass
    gdf_edges = ox.graph_to_gdfs(G, nodes=False)
    return gdf_edges.reset_index()


def create_demo_segments():
    """Create a small set of synthetic segments when OSM is not available (no osmnx)."""
    # Minimal segments with WKT (SRID 4326-style lon/lat), length_m, road_class, lanes, speed, capacity
    demo = [
        {"segment_id": "seg_0", "geometry_wkt": "LINESTRING (-76.50 42.44, -76.49 42.44)", "length_m": 1000.0, "road_class": "primary", "lanes": 2, "free_flow_speed_kmh": 70.0, "capacity_vph": 3800},
        {"segment_id": "seg_1", "geometry_wkt": "LINESTRING (-76.50 42.45, -76.50 42.44)", "length_m": 800.0, "road_class": "secondary", "lanes": 2, "free_flow_speed_kmh": 60.0, "capacity_vph": 3800},
        {"segment_id": "seg_2", "geometry_wkt": "LINESTRING (-76.49 42.44, -76.48 42.44)", "length_m": 1200.0, "road_class": "residential", "lanes": 1, "free_flow_speed_kmh": 40.0, "capacity_vph": 1900},
    ]
    return pd.DataFrame(demo)


def _road_class_from_highway(highway) -> str:
    # OSM can have multiple values (e.g. "primary;secondary"); take first. Handle array/list.
    if hasattr(highway, "__len__") and not isinstance(highway, str):
        highway = highway[0] if len(highway) else "other"
    try:
        if pd.isna(highway):
            return "other"
    except (ValueError, TypeError):
        return "other"
    s = str(highway).strip().lower()
    return s if s else "other"


def _lanes_from_tags(tags, road_class: str) -> int:
    lanes = 1
    if isinstance(tags, dict) and tags.get("lanes"):
        try:
            if pd.isna(tags["lanes"]):
                raise ValueError()
            lanes = int(float(str(tags["lanes"]).split(";")[0].strip()))
        except (ValueError, TypeError):
            pass
    if lanes < 1:
        lanes = 1
    # Default by class
    if lanes == 1 and road_class in ("motorway", "trunk", "primary", "secondary"):
        lanes = 2
    return lanes


def _parse_maxspeed_to_kmh(value):
    """
    Parse common OSM maxspeed formats to km/h.
    Returns None if not parseable.
    """
    if value is None:
        return None
    # list/array -> take first
    if hasattr(value, "__len__") and not isinstance(value, str):
        value = value[0] if len(value) else None
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (ValueError, TypeError):
        return None

    s = str(value).strip().lower()
    if not s or s in {"none", "signals", "variable", "walk"}:
        return None

    # Split on ";" and take first token
    s = s.split(";")[0].strip()

    is_mph = "mph" in s
    # Extract first number (handles "50", "50 km/h", "30mph", "50.0")
    m = re.search(r"(\d+(\.\d+)?)", s)
    if not m:
        return None
    v = float(m.group(1))
    return v * 1.60934 if is_mph else v


def _free_flow_speed_kmh(tags, road_class: str) -> float:
    if isinstance(tags, dict) and "maxspeed" in tags:
        v = _parse_maxspeed_to_kmh(tags.get("maxspeed"))
        if v is not None and np.isfinite(v) and v > 0:
            return float(v)
    # fallback to road-class defaults
    return float(DEFAULT_SPEED_KMH.get(road_class, DEFAULT_SPEED_KMH["other"]))


def _geodesic_length_m(geom) -> float | None:
    """
    Compute geodesic length in meters from lon/lat geometry.
    Uses pyproj if available. Returns None on failure.
    """
    try:
        from pyproj import Geod
        geod = Geod(ellps="WGS84")
        if geom is None or getattr(geom, "is_empty", False):
            return None
        # Handle LineString / MultiLineString
        if geom.geom_type == "LineString":
            xs, ys = geom.xy  # lon, lat
            return float(abs(geod.line_length(xs, ys)))
        if geom.geom_type == "MultiLineString":
            total = 0.0
            for part in geom.geoms:
                xs, ys = part.xy
                total += float(abs(geod.line_length(xs, ys)))
            return total
    except Exception:
        return None
    return None


# --- Step 2: Build static segment dataset ---
def build_segment_dataset(gdf_edges):
    """Build static street segment dataset with segment_id, geometry (WKT), length, road_class, lanes, free_flow_speed, capacity."""
    rows = []
    seg_idx = 0
    for _, row in gdf_edges.iterrows():
        highway = row.get("highway", "other")
        road_class = _road_class_from_highway(highway)
        tags = row if isinstance(row, dict) else row.to_dict()
        lanes = _lanes_from_tags(tags, road_class)
        speed_kmh = _free_flow_speed_kmh(tags, road_class)
        street_name = tags.get("name")
        geom = row.get("geometry")
        if geom is None:
            continue
        # Prefer OSMnx-provided edge length (meters). If missing, compute geodesic length from lon/lat.
        length_m = row.get("length")
        try:
            if length_m is not None and not pd.isna(length_m) and float(length_m) > 0:
                length_m = float(length_m)
            else:
                length_m = None
        except Exception:
            length_m = None
        if length_m is None:
            length_m = _geodesic_length_m(geom)
        if length_m is None or not np.isfinite(length_m) or length_m <= 0:
            continue
        segment_id = f"seg_{seg_idx}"
        seg_idx += 1
        capacity_vph = lanes * CAPACITY_VPH_PER_LANE
        wkt_geom = geom.wkt if hasattr(geom, "wkt") else None
        if wkt_geom is None:
            continue
        rows.append({
            "segment_id": segment_id,
            "geometry_wkt": wkt_geom,
            "length_m": round(float(length_m), 2),
            "road_class": road_class,
            "lanes": lanes,
            "free_flow_speed_kmh": round(speed_kmh, 2),
            "capacity_vph": int(capacity_vph),
            "street_name": street_name,
        })
    return pd.DataFrame(rows)


# --- Step 3: Baseline demand ---
def assign_baseline_demand(segments: pd.DataFrame) -> pd.DataFrame:
    """Estimate base traffic demand (veh/h) using road class, lane count, and distance from center."""
    segments = segments.copy()
    try:
        from shapely import wkt as wkt_load
        geoms = [wkt_load.loads(w) for w in segments["geometry_wkt"]]
        midpoints = [g.interpolate(0.5, normalized=True) for g in geoms]
        cx = np.mean([p.x for p in midpoints])
        cy = np.mean([p.y for p in midpoints])
        dist_weights = []
        for g in geoms:
            mid = g.interpolate(0.5, normalized=True)
            d = np.hypot(mid.x - cx, mid.y - cy)
            weight = 1.2 - 0.4 * min(d / 0.05, 1.0)
            dist_weights.append(max(0.6, weight))
        segments["distance_weight"] = dist_weights
    except Exception:
        segments["distance_weight"] = 1.0
    # Class multiplier (primary > residential > service)
    class_mult = {
        "motorway": 1.4, "trunk": 1.3, "primary": 1.2, "secondary": 1.1,
        "tertiary": 1.0, "residential": 1.0, "unclassified": 0.9, "service": 0.7, "other": 0.8,
    }
    segments["class_mult"] = segments["road_class"].map(lambda x: class_mult.get(x, 0.8))
    segments["baseline_demand_vph"] = (
        BASELINE_VPH_PER_LANE * segments["lanes"] * segments["class_mult"] * segments["distance_weight"]
    ).round(1)
    return segments.drop(columns=["distance_weight", "class_mult"], errors="ignore")


# --- Step 4: Temporal demand patterns ---
def get_temporal_multipliers():
    """Daily profiles (hour of day) and weekday vs weekend. Returns (hours array, weekday mult, weekend mult).

    This profile is intentionally not flat within the peaks so that hours like 7, 8, 9, 10
    have distinguishable demand levels for visualization.
    """
    hour_mult = np.ones(24)

    # Overnight very low
    for h in range(0, 5):
        hour_mult[h] = 0.4

    # Early morning ramp-up
    hour_mult[5] = 0.7
    hour_mult[6] = 0.9

    # AM peak with stronger shape (7 highest, then taper)
    hour_mult[7] = 1.6
    hour_mult[8] = 1.4
    hour_mult[9] = 1.2
    hour_mult[10] = 1.0

    # Late morning / midday
    hour_mult[11] = 0.95
    hour_mult[12] = 1.05
    hour_mult[13] = 1.0
    hour_mult[14] = 0.95

    # Afternoon build-up
    hour_mult[15] = 1.05
    hour_mult[16] = 1.25

    # PM peak with stronger shape
    hour_mult[17] = 1.55
    hour_mult[18] = 1.35
    hour_mult[19] = 1.15

    # Evening wind-down
    hour_mult[20] = 0.85
    hour_mult[21] = 0.7

    # Late evening very low
    for h in range(22, 24):
        hour_mult[h] = 0.45
    weekday_mult = 1.0
    weekend_mult = 0.85
    return hour_mult, weekday_mult, weekend_mult


# --- Step 5: Generate synthetic flow per (segment, timestamp) ---
def generate_flow_timeseries(segments: pd.DataFrame, start_date: datetime, resolution_hours: float, num_days: int, seed: int):
    """For each (segment, timestamp) compute flow with richer temporal structure:
    - Hour-of-day profile with shaped peaks
    - Day-of-week variation
    - Road-class-specific peak emphasis
    - Segment-specific AM/PM bias
    - Extra amplification on the busiest segments during peaks
    """
    rng = np.random.RandomState(seed)
    hour_mult, weekday_mult, weekend_mult = get_temporal_multipliers()
    # Day-of-week multipliers (0=Mon .. 6=Sun)
    dow_mult = np.array([1.05, 1.0, 1.0, 1.0, 1.05, 0.9, 0.85])

    # Road-class-specific peak emphasis factors
    cls = segments["road_class"].astype(str).str.lower().values
    primary_like = np.isin(cls, ["motorway", "trunk", "primary", "secondary"])
    residential_like = np.isin(cls, ["residential", "living_street", "unclassified"])
    service_like = np.isin(cls, ["service", "other"])

    # Segment-specific AM/PM biases (wider range for stronger differentiation)
    am_bias = rng.uniform(0.7, 1.4, size=len(segments))
    pm_bias = rng.uniform(0.7, 1.4, size=len(segments))
    segments = segments.copy()
    segments["am_bias"] = am_bias
    segments["pm_bias"] = pm_bias

    # Mark busiest segments for extra peak amplification (top 10% by baseline demand)
    busy_threshold = np.quantile(segments["baseline_demand_vph"].values, 0.9)
    busy_mask = segments["baseline_demand_vph"].values >= busy_threshold

    # Build timestamp index
    n_intervals = int(num_days * 24 / resolution_hours)
    timestamps = [start_date + timedelta(hours=resolution_hours * i) for i in range(n_intervals)]
    segment_ids = segments["segment_id"].tolist()
    base_demands = segments["baseline_demand_vph"].values
    capacity = segments["capacity_vph"].values

    rows = []
    for ts in timestamps:
        h = ts.hour
        wd = ts.weekday()  # 0=Mon .. 6=Sun
        base_day_mult = weekend_mult if wd >= 5 else weekday_mult
        # Combine global day-of-week and hour-of-day profiles
        day_mult = base_day_mult * dow_mult[wd]
        base_hour = hour_mult[h]

        for i, seg_id in enumerate(segment_ids):
            base = base_demands[i]
            mult = base_hour * day_mult

            # Road-class-specific emphasis
            if primary_like[i]:
                # Stronger AM/PM peaks for primary-like roads
                if 7 <= h <= 9 or 17 <= h <= 19:
                    mult *= 1.2
            elif residential_like[i]:
                # Slightly later / softer peaks for residential
                if 8 <= h <= 10 or 18 <= h <= 20:
                    mult *= 1.1
            elif service_like[i]:
                # Flatter profile for service/other
                if 11 <= h <= 15:
                    mult *= 1.05

            # Segment-specific AM/PM bias
            bias = 1.0
            if 6 <= h <= 10:
                bias *= am_bias[i]
            if 16 <= h <= 19:
                bias *= pm_bias[i]

            noise = rng.uniform(0.92, 1.08)
            flow = max(0, base * mult * bias * noise)

            # Extra amplification for the busiest segments during peaks to create a clearer tail
            if busy_mask[i] and (7 <= h <= 9 or 17 <= h <= 19):
                flow *= 1.7

            # Cap at capacity (optional, BPR handles v/c > 1 but capping avoids extreme values)
            flow = min(flow, capacity[i] * 1.05)
            rows.append({
                "segment_id": seg_id,
                "timestamp": ts.isoformat(),
                "flow_vph": round(flow, 2),
            })
    return pd.DataFrame(rows), segments


# --- Step 6: BPR flow -> speed and travel time ---
def apply_bpr(observations: pd.DataFrame, segments: pd.DataFrame, alpha: float, beta: float):
    """BPR: t = t0 * (1 + alpha * (v/c)^beta). Speed = length_m / t_sec, travel_time_sec = t."""
    seg = segments.set_index("segment_id")
    t0_sec = (seg["length_m"] / 1000) / (seg["free_flow_speed_kmh"] / 3600)  # length in km, speed in km/h -> time in sec
    cap = seg["capacity_vph"]
    length_m = seg["length_m"]

    out = []
    for _, row in observations.iterrows():
        seg_id = row["segment_id"]
        v = row["flow_vph"]
        c = cap.loc[seg_id]
        t0 = t0_sec.loc[seg_id]
        if c <= 0:
            ratio = 0
        else:
            ratio = min(v / c, 3.0)  # cap ratio for numerical stability
        t_sec = t0 * (1 + alpha * (ratio ** beta))
        if not np.isfinite(t_sec) or t_sec <= 0:
            speed_kmh = np.nan
            t_sec_out = np.nan
        else:
            speed_kmh = (length_m.loc[seg_id] / 1000) / (t_sec / 3600)
            t_sec_out = t_sec
        out.append({
            "segment_id": seg_id,
            "timestamp": row["timestamp"],
            "flow_vph": row["flow_vph"],
            "speed_kmh": round(speed_kmh, 2) if np.isfinite(speed_kmh) else np.nan,
            "travel_time_sec": round(t_sec_out, 2) if np.isfinite(t_sec_out) else np.nan,
        })
    return pd.DataFrame(out)


# --- Step 7: Export CSVs ---
def export_csvs(segments: pd.DataFrame, observations: pd.DataFrame, out_segments: str, out_observations: str):
    """Write road_segments.csv and traffic_observations.csv for Supabase (ISO 8601 timestamps)."""
    os.makedirs(os.path.dirname(out_segments) or ".", exist_ok=True)
    # Drop geometry if we want a smaller segments CSV for DB (geometry can be in separate column or same)
    segments_export = segments[[c for c in segments.columns if c != "baseline_demand_vph"]]
    segments_export.to_csv(out_segments, index=False, date_format=None)
    observations.to_csv(out_observations, index=False, date_format=None)
    print(f"Wrote {out_segments} ({len(segments)} rows)")
    print(f"Wrote {out_observations} ({len(observations)} rows)")


# --- Validation ---
def validate(segments: pd.DataFrame, observations: pd.DataFrame) -> bool:
    """Check segment IDs match and observation timestamps are present."""
    seg_ids = set(segments["segment_id"])
    obs_ids = set(observations["segment_id"])
    missing_in_obs = seg_ids - obs_ids
    extra_in_obs = obs_ids - seg_ids
    ok = True
    if missing_in_obs:
        print(f"Warning: segments in road_segments but not in observations: {len(missing_in_obs)}")
        ok = False
    if extra_in_obs:
        print(f"Warning: segment_ids in observations not in road_segments: {extra_in_obs}")
        ok = False
    if observations["timestamp"].isna().any():
        print("Warning: missing timestamps in observations")
        ok = False
    if ok:
        print("Validation passed: segment IDs consistent, timestamps present.")
    return ok


def run_pipeline(use_demo: bool = False, local_osm_override: str = None):
    """Run full pipeline 1->7 and validation. Set use_demo=True to skip OSM. Use local_osm_override to force a specific input file."""
    start = datetime(2025, 3, 3, 0, 0, 0)  # Start date for synthetic series
    osm_path = local_osm_override or LOCAL_OSM_FILE

    if use_demo or not HAS_OSMNX:
        print("Using demo segments (no OSM).")
        segments = create_demo_segments()
    else:
        print("Step 1: Loading road network (local file or OSM)...")
        gdf_edges = extract_road_network(OSM_PLACE, local_osm_path=osm_path)
        print("Step 2: Building static segment dataset...")
        print(f"  Loaded {len(gdf_edges)} edges from OSM.")
        segments = build_segment_dataset(gdf_edges)
        print(f"  Built {len(segments)} segments.")
        if segments.empty:
            print("No segments produced. Check OSM place and graph.")
            sys.exit(1)

    print("Step 3: Assigning baseline demand...")
    segments = assign_baseline_demand(segments)

    print("Step 4 & 5: Generating synthetic flow time series...")
    observations, segments = generate_flow_timeseries(
        segments, start, TIME_RESOLUTION_HOURS, TIME_RANGE_DAYS, RANDOM_SEED
    )

    print("Step 6: Applying BPR for speed and travel time...")
    observations = apply_bpr(observations, segments, BPR_ALPHA, BPR_BETA)

    print("Step 7: Exporting CSVs...")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(base_dir)
    out_seg = os.path.join(project_root, OUTPUT_ROAD_SEGMENTS_CSV)
    out_obs = os.path.join(project_root, OUTPUT_TRAFFIC_OBSERVATIONS_CSV)
    export_csvs(segments, observations, out_seg, out_obs)

    print("Validation...")
    validate(segments, observations)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Generate road_segments.csv and traffic_observations.csv for Supabase")
    p.add_argument("--demo", action="store_true", help="Use synthetic demo segments instead of OSM")
    p.add_argument("--input", type=str, default=None, help="Use this OSM file from data_pipeline/input/ (e.g. houghton.osm)")
    args = p.parse_args()
    input_override = None
    if args.input:
        input_override = os.path.join("data_pipeline", "input", args.input)
    run_pipeline(use_demo=args.demo or not HAS_OSMNX, local_osm_override=input_override)
