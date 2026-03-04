"""
Configuration for the CSV/Supabase traffic data pipeline.
Documented for reproducibility (midterm and README).
"""

# OSM extract: place name for osmnx (used only when LOCAL_OSM_FILE is not set)
OSM_PLACE = "Bar Harbor, Maine, USA"

# Optional: path to a local OSM file (relative to project root). If set and file exists,
# the pipeline loads the network from this file instead of querying OSM at runtime.
LOCAL_OSM_FILE = "data_pipeline/input/bar_harbor.osm"

# When loading from a local OSM file: "drive" = driveable only (fewer segments),
# "all" = all ways including footways/paths (more segments). Online OSM_PLACE always uses "drive".
OSM_NETWORK_TYPE = "all"

# Time resolution: interval for traffic observations (hours)
TIME_RESOLUTION_HOURS = 1
# Time range: number of days to generate (e.g. 7 = one week)
TIME_RANGE_DAYS = 7

# BPR formula: t = t0 * (1 + BPR_ALPHA * (v/c)^BPR_BETA)
# t = travel time, t0 = free-flow travel time, v = flow (veh/h), c = capacity (veh/h)
BPR_ALPHA = 0.15
BPR_BETA = 4.0

# Random seed for reproducible synthetic flow variation
RANDOM_SEED = 42

# Capacity: default vehicles per hour per lane (HCM-style default)
CAPACITY_VPH_PER_LANE = 1900

# Free-flow speed by road class (km/h) when not in OSM
DEFAULT_SPEED_KMH = {
    "motorway": 100,
    "trunk": 90,
    "primary": 70,
    "secondary": 60,
    "tertiary": 50,
    "residential": 40,
    "unclassified": 40,
    "service": 30,
    "other": 40,
}

# Baseline demand: vehicles per hour per lane at "full" baseline (scaled by temporal later)
BASELINE_VPH_PER_LANE = 400

# Output paths (relative to project root)
OUTPUT_ROAD_SEGMENTS_CSV = "data_pipeline/output/road_segments.csv"
OUTPUT_TRAFFIC_OBSERVATIONS_CSV = "data_pipeline/output/traffic_observations.csv"
