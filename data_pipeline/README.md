# Traffic data pipeline (CSV for Supabase)

Implements the 7-step strategy in [.cursor/rules/csv-supabase-data-strategy.mdc](../.cursor/rules/csv-supabase-data-strategy.mdc).

## Decisions (from strategy analysis)

- **Time resolution**: 1 hour (`TIME_RESOLUTION_HOURS` in `config.py`)
- **BPR**: `t = t0 * (1 + alpha * (v/c)^beta)` with `alpha=0.15`, `beta=4` (see `config.py`)
- **Geometry**: WKT in CSV; use SRID 4326 when loading into PostGIS
- **Segment ID**: Stable integer-based IDs (`seg_0`, `seg_1`, ...)
- **Capacity**: Lane-based default 1900 veh/h/lane (`CAPACITY_VPH_PER_LANE`)
- **Reproducibility**: `RANDOM_SEED`, OSM place, and BPR params documented in `config.py`

## Run

From project root:

```bash
pip install -r requirements.txt
cd data_pipeline && python generate_traffic_data.py
```

Outputs (under `data_pipeline/output/`):

- `road_segments.csv`: segment_id, geometry_wkt, length_m, road_class, lanes, free_flow_speed_kmh, capacity_vph
- `traffic_observations.csv`: segment_id, timestamp (ISO 8601), flow_vph, speed_kmh, travel_time_sec

## Validation

The script checks that every segment in `road_segments` appears in `traffic_observations` and that timestamps are present.

## OSM place and local file

Default: the pipeline uses **Echternach, Luxembourg** (`OSM_PLACE` in `config.py`). If you add a local OSM file, set `LOCAL_OSM_FILE` in `config.py` to its path (e.g. `"data_pipeline/input/echternach.osm.pbf"`). If that path exists, the pipeline loads from the file instead of querying OSM online.
