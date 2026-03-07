# Simple: Traffic System Explained (ELI5 + Variable Reference)

**Purpose:** This doc explains the Bar Harbor Traffic system in plain language and lists every variable so you can write full, user-friendly documentation.

---

## Part 1: What This System Does (ELI5)

Imagine you have:

1. **A map of roads** (street segments, like “Main St from A to B”).
2. **Synthetic traffic counts** (how many cars per hour on each segment, every hour, for a week).
3. **A formula (BPR)** that turns “cars per hour” into “how fast are cars going?” and “how long does the segment take?”
4. **A database (Supabase)** that stores the roads and the counts.
5. **An API** that reads the database and adds speed/travel time using the formula.
6. **A dashboard (Streamlit)** that shows maps, charts, and rankings.

**In one sentence:** The data pipeline creates fake-but-realistic traffic data for a road network, the API serves it from Supabase and computes speed/travel time, and the app visualizes it.

---

## Part 2: The Big Picture (How Data Flows)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  DATA PIPELINE (data_pipeline/)                                              │
│  OSM or demo → road segments + raw flow (segment_id, timestamp, flow_vph)   │
│  Outputs: road_segments.csv, traffic_observations.csv                        │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │ upload CSVs
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  SUPABASE (PostgreSQL)                                                       │
│  Tables: road_segments, traffic_observations (raw: segment_id, timestamp,    │
│          flow_vph only; no speed/travel_time in DB)                          │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │ REST API (Supabase client)
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  BAR HARBOR TRAFFIC REPORT API (supabase and api/)                           │
│  GET /segments → passthrough from DB                                         │
│  GET /observations → fetch raw obs + apply BPR → return flow, speed_kmh,     │
│                     travel_time_sec                                         │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │ HTTP JSON
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  STREAMLIT APP (app/)                                                        │
│  Loads from API (or local CSVs), shows congestion map, time series,         │
│  segment ranking, hourly profile, road-class bar chart                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key idea:** Speed and travel time are **not** stored in the database. They are computed in the **API** (and optionally in the app when using local CSVs) using the BPR formula.

---

## Part 3: Every Variable and Field (Reference)

### 3.1 Data pipeline – `config.py`

| Variable | Type | Meaning |
|----------|------|--------|
| `OSM_PLACE` | str | Place name for OSM (e.g. `"Bar Harbor, Maine, USA"`) when not using a local file. |
| `LOCAL_OSM_FILE` | str | Path to local OSM file (e.g. `"data_pipeline/input/bar_harbor.osm"`). If set and file exists, pipeline uses it instead of querying OSM. |
| `OSM_NETWORK_TYPE` | str | `"drive"` or `"all"`. When using local OSM file: `"all"` = all ways; online OSM usually uses `"drive"`. |
| `TIME_RESOLUTION_HOURS` | float | Interval between observation timestamps (e.g. `1` = hourly). |
| `TIME_RANGE_DAYS` | int | Number of days of synthetic data (e.g. `7` = one week). |
| `BPR_ALPHA` | float | BPR formula parameter: `t = t0 * (1 + alpha * (v/c)^beta)`. Default `0.15`. |
| `BPR_BETA` | float | BPR formula parameter (default `4.0`). |
| `RANDOM_SEED` | int | Seed for reproducible random variation in flow (e.g. `42`). |
| `CAPACITY_VPH_PER_LANE` | int | Default capacity in vehicles per hour per lane (e.g. `1900`). Segment capacity = lanes × this. |
| `DEFAULT_SPEED_KMH` | dict | Free-flow speed (km/h) by road class when OSM has no maxspeed (e.g. motorway 100, residential 40). |
| `BASELINE_VPH_PER_LANE` | int | Base demand in veh/h per lane before temporal scaling (e.g. `400`). |
| `OUTPUT_ROAD_SEGMENTS_CSV` | str | Path for output segments CSV (e.g. `"data_pipeline/output/road_segments.csv"`). |
| `OUTPUT_TRAFFIC_OBSERVATIONS_CSV` | str | Path for output observations CSV (e.g. `"data_pipeline/output/traffic_observations.csv"`). |

---

### 3.2 Data pipeline – segment and observation fields (generated)

**Road segments (per row):**

| Field | Type | Meaning |
|-------|------|--------|
| `segment_id` | str | Unique ID (e.g. `seg_0`, `seg_1`). |
| `geometry_wkt` | str | Line geometry as WKT (e.g. `LINESTRING (lon lat, ...)`). |
| `length_m` | float | Segment length in meters. |
| `road_class` | str | OSM highway type: motorway, trunk, primary, secondary, tertiary, residential, unclassified, service, other, etc. |
| `lanes` | int | Number of lanes (defaults by road class if not in OSM). |
| `free_flow_speed_kmh` | float | Speed (km/h) with no congestion (from OSM maxspeed or `DEFAULT_SPEED_KMH`). |
| `capacity_vph` | int | Capacity in vehicles per hour (lanes × `CAPACITY_VPH_PER_LANE`). |
| `street_name` | str or None | Street name from OSM, if any. |
| `baseline_demand_vph` | float | Used only inside pipeline; not exported to CSV (used to generate flow). |

**Traffic observations (per row) – raw sensor data in CSV/DB:**

| Field | Type | Meaning |
|-------|------|--------|
| `segment_id` | str | Links to `road_segments.segment_id`. |
| `timestamp` | datetime/str | Time of observation (ISO 8601). |
| `flow_vph` | float | Vehicles per hour (synthetic flow). |

**Observations after BPR (in API or app):**

| Field | Type | Meaning |
|-------|------|--------|
| `segment_id` | str | Same as above. |
| `timestamp` | str | Same as above. |
| `flow_vph` | float | Same as above. |
| `speed_kmh` | float | Speed in km/h from BPR (derived). |
| `travel_time_sec` | float | Travel time in seconds (derived). |

---

### 3.3 Supabase – SQL schema (`SQL_query`)

**Table: `road_segments`**

| Column | Type | Meaning |
|--------|------|--------|
| `segment_id` | TEXT PK | Same as pipeline. |
| `geometry_wkt` | TEXT | Same as pipeline. |
| `length_m` | NUMERIC | Same as pipeline. |
| `road_class` | TEXT | Same as pipeline. |
| `lanes` | INTEGER | Same as pipeline. |
| `free_flow_speed_kmh` | NUMERIC | Same as pipeline. |
| `capacity_vph` | INTEGER | Same as pipeline. |
| `street_name` | TEXT | Same as pipeline. |
| `am_bias` | NUMERIC | Optional; some pipelines add AM peak bias (not in generic pipeline). |
| `pm_bias` | NUMERIC | Optional; PM peak bias (not in generic pipeline). |

**Table: `traffic_observations`**

| Column | Type | Meaning |
|--------|------|--------|
| `id` | BIGSERIAL PK | Auto-generated row ID. |
| `segment_id` | TEXT FK | References `road_segments(segment_id)`. |
| `timestamp` | TIMESTAMPTZ | Time of observation. |
| `flow_vph` | NUMERIC | Vehicles per hour (raw; no speed/travel_time in DB). |

RLS is enabled; policies allow public read for both tables.

---

### 3.4 API – environment and code

**Environment variables (from `.env` or Connect):**

| Variable | Meaning |
|----------|--------|
| `SUPABASE_URL` | Supabase project URL (e.g. `https://xxx.supabase.co`). |
| `SUPABASE_ANON_KEY` | Supabase anon/public API key. |

**`api/supabase_client.py`:**

| Name | Meaning |
|------|--------|
| `_PAGE_SIZE` | Pagination chunk size (1000; PostgREST default). |
| `_get_headers()` | Builds `apikey`, `Authorization`, `Accept` from env. |
| `_fetch_all_pages()` | GETs a REST URL with `Range` and `Prefer: count=exact` to retrieve all rows. |
| `fetch_road_segments()` | Returns list of dicts from `road_segments`. |
| `fetch_traffic_observations()` | Returns list of dicts from `traffic_observations`. |

**`api/schemas.py` (Pydantic response models):**

| Model / Field | Meaning |
|---------------|--------|
| **RoadSegment** | One row of road segment. |
| → `segment_id` | str |
| → `geometry_wkt` | str \| None |
| → `length_m` | float \| None |
| → `road_class` | str \| None |
| → `lanes` | int \| None |
| → `free_flow_speed_kmh` | float \| None |
| → `capacity_vph` | int \| None |
| → `am_bias` | float \| None |
| → `pm_bias` | float \| None |
| → `street_name` | str \| None |
| **TrafficObservation** | One observation with BPR fields. |
| → `segment_id` | str |
| → `timestamp` | str |
| → `flow_vph` | float |
| → `speed_kmh` | float \| None (from BPR) |
| → `travel_time_sec` | float \| None (from BPR) |

**`api/routers/traffic.py`:**

| Name | Meaning |
|------|--------|
| `get_segments()` | GET /segments: fetches segments from Supabase, returns list of `RoadSegment`. |
| `get_observations()` | GET /observations: fetches segments + observations, runs BPR, returns list of `TrafficObservation` with `speed_kmh`, `travel_time_sec`. |
| `_missing_supabase_config()` | True if `SUPABASE_URL` or `SUPABASE_ANON_KEY` is missing. |

**`bpr.py`:**

| Name | Meaning |
|------|--------|
| `BPR_ALPHA` | Same as config (0.15). |
| `BPR_BETA` | Same as config (4.0). |
| `apply_bpr(observations, segments, alpha, beta)` | Input: observations with `segment_id`, `flow_vph` (and optionally `timestamp`); segments with `segment_id`, `length_m`, `free_flow_speed_kmh`, `capacity_vph`. Output: same rows plus `speed_kmh`, `travel_time_sec`. Formula: `t = t0 * (1 + alpha * (v/c)^beta)`; `speed_kmh = (length_m/1000) / (t_sec/3600)`. |

---

### 3.5 Streamlit app – `app/streamlit_app.py`

**Constants and paths:**

| Name | Meaning |
|------|--------|
| `DRIVEABLE` | Set of road_class values treated as driveable (motorway, primary, residential, etc.); used to filter segments. |
| `REPO_ROOT` | Project root (parent of `app/`). |
| `OUTPUT_DIR` | `data_pipeline/output`. |
| `SEGMENTS_CSV` | `OUTPUT_DIR/road_segments.csv`. |
| `OBSERVATIONS_CSV` | `OUTPUT_DIR/traffic_observations.csv`. |
| `DEFAULT_API_BASE` | Default API URL; from env `TRAFFIC_API_BASE_URL` or a Posit Connect URL. |

**Data loading:**

| Name | Meaning |
|------|--------|
| `_fetch_from_api(base_url, path)` | GET JSON from `base_url/path`; returns None on failure. |
| `load_segments(api_base)` | If `api_base` set: GET segments from API; else read `SEGMENTS_CSV`. Cached. |
| `load_observations(api_base)` | If `api_base` set: GET observations from API (already with BPR); else read `OBSERVATIONS_CSV` and apply BPR locally if needed. Cached. |
| `_apply_bpr(observations, segments, alpha, beta)` | Same BPR as API: adds `speed_kmh`, `travel_time_sec` to observations DataFrame. |

**Geometry:**

| Name | Meaning |
|------|--------|
| `wkt_to_latlon_pairs(wkt_str)` | Parses WKT to list of (lat, lon) pairs for map center. |
| `wkt_to_lonlat_path(wkt_str)` | Parses WKT to list of [lon, lat] for pydeck PathLayer. |

**UI / state (sidebar and main):**

| Name | Meaning |
|------|--------|
| `use_api` | Checkbox: load from API (true) or local CSV (false). |
| `api_base` | Text input: API base URL when using API. |
| `driveable_only` | Checkbox: filter to driveable road classes only. |
| `cong_mode` | Radio: "All times" or "Specific hour". |
| `cong_hour` | Slider 0–23 when cong_mode is "Specific hour". |
| `day_filter` | Radio: "All days", "Weekdays (Mon–Fri)", "Weekends (Sat–Sun)". |

**Derived DataFrames / columns used in UI:**

| Name | Meaning |
|------|--------|
| `segments` | Filtered segment list (optionally driveable-only). |
| `observations` | Filtered observations (optionally by day_filter). |
| `seg_stats` | Copy of observations; if cong_hour set, filtered to that hour. |
| `mean_flow_by_seg` | groupby segment_id, mean(flow_vph). |
| `segments_with_vc` | segments + mean_flow_vph + vc_ratio (mean_flow_vph / capacity_vph). |
| `vc_ratio` | flow/capacity for congestion coloring. |
| `obs_cap` | observations merged with capacity_vph; has vc_ratio_all. |
| `q10, q30, q50, q65, q80, q90, q97` | Quantiles of v/c for color scale (congestion map). |
| `seg_for_congestion` | Segments with `path` (lon/lat list) and `color` (RGB from v/c). |
| `agg` | observations grouped by timestamp: mean flow_vph, mean speed_kmh. |
| `ranking` | segments + mean_flow_vph, score = mean_flow_vph × length_m; top 30. |
| `hourly` | observations by hour of day: mean flow_vph, mean speed_kmh. |
| `by_class` | segments grouped by road_class, count. |

**Metrics shown:** Segments count, total observation rows, time range, avg flow (veh/h), avg speed (km/h).

---

## Part 4: How the Pieces Integrate

1. **Pipeline → CSVs**  
   Pipeline uses `config.py` and (optionally) OSM to produce `road_segments.csv` and `traffic_observations.csv`. Observations in CSV/DB are **raw**: `segment_id`, `timestamp`, `flow_vph` only.

2. **CSVs → Supabase**  
   You run the SQL in `SQL_query` to create tables, then upload the CSVs. Column names in CSV must match the SQL schema (segment_id, geometry_wkt, length_m, road_class, lanes, free_flow_speed_kmh, capacity_vph, street_name; and for observations: segment_id, timestamp, flow_vph).

3. **Supabase → API**  
   API reads `road_segments` and `traffic_observations` via Supabase REST (paginated). For GET /observations it joins in code and runs `bpr.apply_bpr()` so responses include `speed_kmh` and `travel_time_sec`.

4. **API → App**  
   App calls GET /segments and GET /observations when "Load from API" is on, and uses the same variable names (segment_id, flow_vph, speed_kmh, travel_time_sec, timestamp, etc.). If loading from CSV, app uses the same column names and applies BPR locally so the rest of the app is identical.

5. **BPR in two places**  
   - **API:** `traffic.get_observations()` uses `bpr.apply_bpr()` so every GET /observations response has BPR fields.  
   - **App:** When using local CSVs, `load_observations()` calls `_apply_bpr()` if `speed_kmh` is missing.  
   Use the same BPR constants (e.g. alpha=0.15, beta=4.0) in pipeline config, API bpr.py, and app `_apply_bpr` for consistent numbers.

6. **Segment ID is the join key**  
   Everywhere: pipeline, DB, API, and app use `segment_id` to link observations to segments (geometry, length_m, capacity_vph, free_flow_speed_kmh).

---

## Part 5: Checklist for Full User Documentation

You can use this to build a full doc set:

- [ ] **Overview** – One-page “what this system does” (like Part 1).
- [ ] **Architecture** – Diagram and short description of pipeline → DB → API → app (like Part 2).
- [ ] **Setup** – Python version, `pip install -r requirements.txt`, `.env` (SUPABASE_*, TRAFFIC_API_BASE_URL for app).
- [ ] **Data pipeline** – How to run (e.g. `python "generate_traffic_data BARHARBOR.py"` or `--demo`), what config.py does, where CSVs are written.
- [ ] **Database** – Run `SQL_query` in Supabase, upload CSVs, list tables and columns (Part 3.3).
- [ ] **API** – Endpoints GET /segments and GET /observations, env vars, local run (`uvicorn api_main:app`), deploy (e.g. Posit Connect).
- [ ] **App** – Run (`streamlit run app/streamlit_app.py`), data source (API vs CSV), sidebar options (driveable only, hour, day filter).
- [ ] **Variable / field glossary** – Copy or adapt Part 3 for a “Reference” section.
- [ ] **BPR** – One short section: formula, where it’s applied (API; app for CSV), and that DB stores only raw flow.
- [ ] **Troubleshooting** – Missing .env, missing CSVs, API 503, empty map (e.g. wrong API URL or no driveable segments).

---

## Part 6: File Map (Where to Find What)

| What | Where |
|------|--------|
| Pipeline config (time range, BPR, capacity, paths) | `data_pipeline/config.py` |
| Pipeline logic (OSM → segments → demand → flow → CSV) | `data_pipeline/generate_traffic_data generic.py` or `generate_traffic_data BARHARBOR.py` |
| DB table definitions | `supabase and api/SQL_query` |
| Supabase REST client | `supabase and api/api/supabase_client.py` |
| API routes and BPR call | `supabase and api/api/routers/traffic.py` |
| BPR formula | `supabase and api/bpr.py` |
| API response shapes | `supabase and api/api/schemas.py` |
| App entry, data source, maps, charts | `app/streamlit_app.py` |
| API env example | `supabase and api/.env.example` |
| Deploy config (FastAPI) | `supabase and api/manifest.json` |

---

*Simple.md – variable reference and integration guide for the Bar Harbor Traffic system.*
