# MidtermSYSEN

This project builds a synthetic traffic pipeline and dashboard for a real city road network, suitable for Supabase/PostgreSQL + REST API + Streamlit.

## Data pipeline (`data_pipeline/`)

- **`config.py`**
  - Controls:
    - Input OSM file (currently `data_pipeline/input/bar_harbor.osm`)
    - Time resolution, number of days
    - BPR parameters (`BPR_ALPHA`, `BPR_BETA`)
    - Capacity per lane and default free‑flow speeds by `road_class`

- **`generate_traffic_data BARHARBOR.py`** (or generic script)
  - Loads an OSM network (via OSMnx) and builds:
    - `road_segments.csv` with:
      - `segment_id`, `geometry_wkt`, `length_m` (meters), `road_class`, `lanes`
      - `free_flow_speed_kmh`, `capacity_vph`
      - `am_bias`, `pm_bias` (segment‑specific AM/PM multipliers)
    - `traffic_observations.csv` as **raw sensor data**: `segment_id`, `timestamp`, `flow_vph` only (no speed/travel time; BPR is applied in the API layer).
  - Flow generation includes hour‑of‑day profile, day‑of‑week variation, road‑class and segment‑specific multipliers.
  - Writes the two CSVs under `data_pipeline/output/` and validates segment IDs and timestamps.

- **How to regenerate CSVs**

```bash
cd data_pipeline
python3 generate_traffic_data.py
```

Outputs:

- `data_pipeline/output/road_segments.csv`
- `data_pipeline/output/traffic_observations.csv`

## Bar Harbor Traffic Report API (`supabase and api/`)

FastAPI service that reads road segments and traffic observations from Supabase and exposes:

- **`GET /segments`** — passthrough to `road_segments` table.
- **`GET /observations`** — traffic observations with BPR-derived `speed_kmh` and `travel_time_sec`.

Set `SUPABASE_URL` and `SUPABASE_ANON_KEY` (see `supabase and api/.env.example`). Run locally from the `supabase and api` directory:

```bash
uvicorn api_main:app --reload
```

Deploy to Posit Connect (flat): `rsconnect deploy fastapi -n <server> --entrypoint api_main:app "supabase and api/"`

Deployed API via Cornell Posit Server: https://connect.systems-apps.com/content/4579a545-541d-412e-93d4-b35ef9cbca66/docs

## Dashboard (`app/streamlit_app.py`)

The Streamlit app visualizes congestion patterns from local CSVs or the Bar Harbor Traffic Report API.

- **Data source**
  - **Local**: reads `road_segments.csv` and `traffic_observations.csv` from `data_pipeline/output/`.
  - **API**: enable “Load from API” in the sidebar and set the API base URL (e.g. `http://127.0.0.1:8000` or your deployed API). When you deploy the dashboard, set the env var **`TRAFFIC_API_BASE_URL`** to your deployed API URL so the default points there and “Load from API” is on by default—no code change needed.

- **Sidebar filters**
  - **Driveable roads only** (default): filters to typical car‑usable `road_class` values.
  - **Congestion period**
    - All times
    - Specific hour (0–23 slider)
  - **Days included**
    - All days
    - Weekdays (Mon–Fri)
    - Weekends (Sat–Sun)

- **Visuals**
  - **Metrics row**: number of segments, time range, average flow, average speed.
  - **Congestion map (pydeck PathLayer)**:
    - Colors are based on **absolute v/c** (`flow_vph / capacity_vph`) for the current hour and day filter.
    - Color bands (green → yellow → orange → red) are derived from full‑day v/c quantiles (after day‑of‑week filter),
      so peak hours naturally appear “hotter” than off‑peak hours on a global scale.
  - **Traffic over time**:
    - Dual‑axis plot of mean flow and mean speed vs time.
  - **Segment ranking (prioritization)**:
    - Top 30 segments by `mean_flow_vph × length_m` (vehicle‑miles proxy).
  - **Hourly profile**:
    - Mean flow and mean speed by hour of day (0–23).

- **How to run the dashboard**

From the project root:

```bash
streamlit run app/streamlit_app.py
```

This will open the app in your browser (default: `http://localhost:8501`).