# MidtermSYSEN

This project builds a synthetic traffic pipeline and dashboard for a real city road network, suitable for Supabase/PostgreSQL + REST API + Streamlit.

## Data pipeline (`data_pipeline/`)

- **`config.py`**
  - Controls:
    - Input OSM file (currently `data_pipeline/input/bar_harbor.osm`)
    - Time resolution, number of days
    - BPR parameters (`BPR_ALPHA`, `BPR_BETA`)
    - Capacity per lane and default free‑flow speeds by `road_class`

- **`generate_traffic_data.py`**
  - Loads an OSM network (via OSMnx) and builds:
    - `road_segments.csv` with:
      - `segment_id`, `geometry_wkt`, `length_m` (meters), `road_class`, `lanes`
      - `free_flow_speed_kmh`, `capacity_vph`
      - `am_bias`, `pm_bias` (segment‑specific AM/PM multipliers)
    - `traffic_observations.csv` with:
      - `segment_id`, `timestamp`, `flow_vph`, `speed_kmh`, `travel_time_sec`
  - Flow generation includes:
    - Shaped **hour‑of‑day** profile (strong AM and PM peaks with variation between 7–10 and 16–19)
    - **Day‑of‑week** variation (Mon/Fri vs mid‑week vs weekend)
    - **Road‑class‑specific** peak emphasis (primary‑like vs residential vs service)
    - **Segment‑specific AM/PM bias** (stored in the segments CSV)
    - Extra amplification for the busiest segments during peaks (top 10% by baseline demand)
  - Applies a BPR curve to convert flow to speed and travel time.
  - Writes the two CSVs under `data_pipeline/output/` and validates basic consistency.

- **How to regenerate CSVs**

```bash
cd data_pipeline
python3 generate_traffic_data.py
```

Outputs:

- `data_pipeline/output/road_segments.csv`
- `data_pipeline/output/traffic_observations.csv`

## Dashboard (`app/streamlit_app.py`)

The Streamlit app visualizes congestion patterns for the generated CSVs.

- **Data source**
  - Reads `road_segments.csv` and `traffic_observations.csv` from `data_pipeline/output/`.

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

This will open the app in your browser (default: `http://localhost:8501`).*** End Patch```}]]