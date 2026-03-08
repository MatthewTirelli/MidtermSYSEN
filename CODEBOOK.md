# Bar Harbor Congestion Pipeline — Codebook

This codebook describes every file and major variable in the **dashboard app** (`app/`) and the **Traffic API** (`NewAPI/api/`), plus the data and environment you need to collect or use the system.

---

## 1. Pipeline overview

| Layer | Role | Location |
|-------|------|----------|
| **Database** | Stores road segments and traffic observations (flow per segment per time). | Supabase (PostgreSQL) |
| **API** | Reads from Supabase; applies BPR to get speed/travel time; serves segments and traffic windows. | `NewAPI/api/` |
| **Dashboard** | Shiny app: map, KPIs, tables, AI summary. Calls API and Ollama Cloud. | `app/` |

Data flow: **Supabase → NewAPI (BPR) → Dashboard (map/KPIs/AI)**.

---

## 2. Dashboard app (`app/`)

### 2.1 `app/app.py`

Main Shiny for Python application: UI, server logic, map, KPIs, gauge, table, and AI summary.

**Purpose:** Renders the Bar Harbor Congestion Intelligence Dashboard and handles all user interaction and data display.

**Key constants and configuration**

| Name | Type | Description |
|------|------|-------------|
| `DEFAULT_API_BASE` | `str` | Default base URL for the Traffic API (e.g. Posit Connect deployment). |
| `DRIVEABLE` | `set[str]` | OSM road classes to treat as driveable (used when "Driveable roads only" is checked). |
| `ZOOM_LOCATIONS` | `dict` | Named map views: `(lat, lon, zoom)` for "Bar Harbor (overview)" and "Downtown Bar Harbor". |

**Reactive state (server)**

| Name | Type | Description |
|------|------|-------------|
| `segments_df` | `reactive.Value(None)` | Cached road segments from `GET /segments`. |
| `observations_df` | `reactive.Value(None)` | Raw or aggregated observation rows (from API or built from 23 hourly windows in daily mode). |
| `window_stats_df` | `reactive.Value(None)` | Aggregated stats per segment for the current window (from `GET /traffic/window` or daily aggregate). |
| `loading` | `reactive.Value(False)` | Whether a load is in progress. |
| `loading_message` | `reactive.Value("")` | Message shown during load (e.g. "Fetching hour 5/23…"). |
| `api_error` | `reactive.Value(None)` | API error message to show (e.g. missing URL). |
| `ai_summary_text` | `reactive.Value("")` | Text of the AI-generated summary. |
| `ai_loading` | `reactive.Value(False)` | Whether the AI summary request is in progress. |

**Key functions**

| Function | Purpose |
|----------|---------|
| `sanitize_report_text(raw)` | Post-processes LLM output: strips markdown, normalizes punctuation, collapses blank lines. |
| `make_deck(map_df, view_lat, view_lon, view_zoom, daily_mode)` | Builds a PyDeck `Deck` with PathLayer for the congestion map; tooltip content depends on hourly vs daily. |
| `deck_to_embed_html(deck, height, use_iframe)` | Converts the PyDeck map to HTML (optionally base64 iframe) for embedding in Shiny. |
| `_plotly_to_iframe_html(fig, height, div_id, include_plotlyjs)` | Converts a Plotly figure to embeddable HTML for the time-of-day chart. |

**Server logic (reactive calcs and effects)**

| Name | Type | Purpose |
|------|------|---------|
| `_do_load()` | Effect | Fetches segments and traffic data: in **hourly** mode one `GET /traffic/window`; in **daily** mode 23 calls (one per hour), then concatenates and builds daily aggregate and per-hour observations. |
| `observations()` | `@reactive.Calc` | Returns observations filtered by selected date (and hour in hourly mode). |
| `peak_hour_for_map()` | `@reactive.Calc` | In daily mode, returns the network-wide peak congestion hour (0–23) from flow/capacity by hour; used so the daily map shows that single hour. |
| `seg_stats()` | `@reactive.Calc` | Returns per-segment stats: either `window_stats_df` from the API or, when that’s empty, aggregates from `observations()`. In daily mode with per-hour data, adds per-segment `peak_vc` and `peak_hour` for fallback/legacy paths. |
| `map_df()` | `@reactive.Calc` | Builds the map DataFrame: merges segments with stats, adds `path` (from WKT), `color` (from v/c), and tooltip columns. In **daily** mode when peak hour is available, uses only that hour’s data for coloring and tooltips. |
| `_run_ai_summary()` | Effect | Builds prompt from current KPIs and top segments/streets; calls `query_llm(messages)`; sanitizes response and sets `ai_summary_text`. |

**UI elements (outputs)**

- `metric_avg_speed`, `metric_flow`, `metric_third`, `metric_fourth` — KPI cards (labels and values depend on hourly vs daily).
- `map_ui` — Congestion map (PyDeck via iframe).
- `gauge_ui` — Overall congestion gauge (Plotly).
- `plotly_ui` — Time-of-day profile (daily mode only).
- `table_ui` — "Most Congested Roads" table.
- `ai_summary_ui` — AI summary text (or placeholder/error).
- `dataset_badge_ui` — Badge and caption (e.g. "Daily map: showing congestion at peak hour (18:00)").

**Prompts (AI summary)**

- `OLLAMA_SYSTEM_PROMPT`: Instructions for the model (plain text, no markdown, factual only, multiple short sections, street names only).
- User prompt: built from mode, date, hour, top segments/streets list, and KPIs; asks for conversational but factual summary with a clear structure (lead line, 3–5 hotspots, closing advice).

---

### 2.2 `app/api_client.py`

Cached HTTP client for the Bar Harbor Traffic Report API.

**Purpose:** Single place for all dashboard → API calls; in-memory cache keyed by path and query params to avoid duplicate requests.

**Constants**

| Name | Type | Description |
|------|------|-------------|
| `HTTP_TIMEOUT` | `float` | Timeout in seconds for API requests (300). |
| `_api_cache` | `dict` | Module-level cache: key = `_cache_key(path, params)`, value = `(DataFrame, error)`. |

**Functions**

| Function | Returns | Description |
|----------|---------|-------------|
| `_cache_key(path, params)` | `str` | SHA-256 hash of path + JSON-sorted params; used as cache key. |
| `fetch_segments(base_url)` | `(df, error, status_code, num_records)` | `GET {base_url}/segments`; returns DataFrame of road segments or error. |
| `fetch_observations(base_url, limit, date, start_hour, end_hour)` | `(df, error, status_code, num_records)` | `GET {base_url}/observations` with optional filters; parses `timestamp` to datetime. |
| `fetch_traffic_window(base_url, date, start_hour, end_hour)` | `(df, error, status_code, num_records)` | `GET {base_url}/traffic/window`; returns one row per segment with `mean_flow_vph`, `mean_speed_kmh`, `mean_travel_time_sec`, `vc_ratio`. |

**DataFrame columns (from API)**

- **Segments:** `segment_id`, `geometry_wkt`, `length_m`, `road_class`, `lanes`, `free_flow_speed_kmh`, `capacity_vph`, `street_name`, etc.
- **Traffic window:** `segment_id`, `mean_flow_vph`, `mean_speed_kmh`, `mean_travel_time_sec`, `vc_ratio`.

---

### 2.3 `app/llm_cloud.py`

Ollama Cloud chat integration for the AI summary feature.

**Purpose:** Single function to call the Ollama Cloud chat API with Bearer auth; no local Ollama server.

**Environment variables (read at runtime)**

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OLLAMA_API_KEY` | Yes (for AI summary) | — | API key; sent as `Authorization: Bearer <key>`. |
| `OLLAMA_MODEL` | No | `gpt-oss:20b-cloud` | Model name for the chat request. |
| `OLLAMA_TIMEOUT` | No | `90` | Request timeout in seconds. |
| `OLLAMA_CLOUD_URL` | No | `https://ollama.com/api/chat` | Override for the chat endpoint. |

**Constants**

| Name | Description |
|------|-------------|
| `OLLAMA_CLOUD_CHAT_URL` | Resolved from env (default `https://ollama.com/api/chat`). |
| `OLLAMA_TIMEOUT` | Integer timeout from env. |

**Class**

| Name | Description |
|------|-------------|
| `OllamaCloudError` | Exception raised on missing key, non-200, timeout, or malformed response. |

**Functions**

| Function | Purpose |
|----------|---------|
| `_get_api_key()` | Returns `OLLAMA_API_KEY` or raises `OllamaCloudError` with a clear message. |
| `_get_model()` | Returns `OLLAMA_MODEL` or default `gpt-oss:20b-cloud`. |
| `query_llm(messages, model=None, stream=False)` | POSTs to Ollama Cloud with `model`, `messages` (list of `{role, content}`), `stream`; returns `message.content` from the JSON response. Handles timeouts and connection errors. |

**Request/response**

- Request body: `{"model": str, "messages": [...], "stream": bool}`.
- Response: expects `{"message": {"content": "..."}}`; extracts and returns `content` as text.

---

### 2.4 `app/map_utils.py`

Map helpers: WKT parsing, v/c → color, and building the map DataFrame.

**Purpose:** Turn segment geometry and stats into the structure PyDeck’s PathLayer expects (path, color, tooltip fields).

**Constants**

| Name | Type | Description |
|------|------|-------------|
| `BAR_HARBOR_CENTER_LAT` | `float` | Default map center latitude (44.39). |
| `BAR_HARBOR_CENTER_LON` | `float` | Default map center longitude (-68.21). |
| `VC_FREE` | `float` | v/c &lt; 0.5 → green. |
| `VC_MODERATE` | `float` | v/c &lt; 0.7 → yellow. |
| `VC_HEAVY` | `float` | v/c &lt; 0.9 → orange; ≥ 0.9 → red. |

**Functions**

| Function | Purpose |
|----------|---------|
| `wkt_to_lonlat_path(wkt_str)` | Parses WKT LineString/MultiLineString (via Shapely) into a list of `[lon, lat]` pairs for PyDeck. |
| `vc_to_color(vc)` | Maps v/c ratio to RGB list `[r, g, b]` (0–255) for PathLayer. |
| `vc_severity_label(vc)` | Returns "Free flow" | "Moderate" | "Heavy" | "Severe" | "No data". |
| `build_map_data(segments, seg_stats)` | Merges segments with optional stats; adds `path` from `geometry_wkt`, `color` from `vc_ratio`, and `street_name`/`road_class`; returns DataFrame suitable for PyDeck. |

**Segment/stats columns used**

- From segments: `segment_id`, `geometry_wkt`, `street_name`, `road_class`.
- From seg_stats (if provided): `segment_id`, `mean_speed_kmh`, `mean_flow_vph`, `vc_ratio`.

---

## 3. Traffic API (`NewAPI/api/`)

### 3.1 `api/main.py`

FastAPI application entry point and lifespan.

**Purpose:** Mount the traffic router, load `.env`, and warm the segment cache at startup.

**Lifespan**

- On startup: calls `warm_segment_cache()` so `GET /segments` and BPR lookups use in-memory segments.
- On shutdown: (none).

**Routes**

| Method + Path | Handler | Description |
|---------------|---------|-------------|
| `GET /health` | `health()` | Returns `{"status": "ok"}`. |
| `GET /segments` | (router) | See §3.2. |
| `GET /traffic/window` | (router) | See §3.2. |

**Env loading**

- Loads `.env` from: `NewAPI/`, repo root, `supabase and api/` (in that order).

---

### 3.2 `api/routers/traffic.py`

HTTP endpoints for segments and traffic window.

**Purpose:** Expose Supabase-backed segments and BPR-computed traffic metrics per segment per time window.

**Helper**

| Function | Purpose |
|----------|---------|
| `_missing_supabase_config()` | Returns True if `SUPABASE_URL` or `SUPABASE_ANON_KEY` is unset. |

**Endpoints**

| Method + Path | Response model | Description |
|---------------|----------------|--------------|
| `GET /segments` | `list[RoadSegment]` | Returns cached road segments from Supabase (or 503 if config missing). |
| `GET /traffic/window?date=&start_hour=&end_hour=` | `list[TrafficWindowRow]` | One row per segment: `mean_flow_vph`, `mean_speed_kmh`, `mean_travel_time_sec`, `vc_ratio` for the given time window; 503 if Supabase config missing. |

**Dependencies**

- `schemas.RoadSegment`, `schemas.TrafficWindowRow`
- `services.supabase_client.fetch_segments`
- `services.traffic_service.get_traffic_window`

---

### 3.3 `api/schemas.py`

Pydantic models for API responses.

**Purpose:** Type and validate JSON responses for docs and clients.

**Models**

| Model | Fields | Description |
|-------|--------|-------------|
| `RoadSegment` | `segment_id`, `geometry_wkt`, `length_m`, `road_class`, `lanes`, `free_flow_speed_kmh`, `capacity_vph`, `am_bias`, `pm_bias`, `street_name` (all optional except `segment_id`) | One road segment from `road_segments`. |
| `TrafficObservation` | `segment_id`, `timestamp`, `flow_vph`, `speed_kmh`, `travel_time_sec` | Single observation (e.g. from a legacy observations endpoint). |
| `TrafficWindowRow` | `segment_id`, `mean_flow_vph`, `mean_speed_kmh`, `mean_travel_time_sec`, `vc_ratio` | One row per segment from `GET /traffic/window`. |

---

### 3.4 `api/services/traffic_service.py`

Business logic for the traffic window: fetch observations, apply BPR, aggregate by segment.

**Purpose:** Implement `GET /traffic/window`: filter observations by time, join segments, compute speed and travel time with BPR, then aggregate to one row per segment.

**Constants**

| Name | Value | Description |
|------|-------|-------------|
| `REQUIRED_SEG` | `{"segment_id", "length_m", "free_flow_speed_kmh", "capacity_vph"}` | Required segment columns for BPR. |
| `REQUIRED_OBS` | `{"segment_id", "timestamp", "flow_vph"}` | Required observation columns. |

**Functions**

| Function | Purpose |
|----------|---------|
| `_window_to_iso(date, start_hour, end_hour)` | Converts date + hour range to ISO start/end timestamps; returns `None` if invalid. |
| `get_traffic_window(date, start_hour, end_hour)` | Fetches segments and observations for the window; merges obs to segments; runs `apply_bpr_vectorized`; aggregates by `segment_id` (mean flow, mean speed, mean travel time); computes `vc_ratio` = mean_flow / capacity (clipped 0–3); returns list of dicts matching `TrafficWindowRow`. |

**Data flow inside `get_traffic_window`**

1. `_window_to_iso` → start/end ISO strings.
2. `fetch_segments()` → list of segment dicts.
3. `fetch_observations_window(start_iso, end_iso)` → list of observation dicts.
4. Build DataFrames; merge observations to segment index (`seg_idx`).
5. `apply_bpr_vectorized(seg_idx, flow_vph, length_m, free_flow_speed_kmh, capacity_vph)` → `speed_kmh`, `travel_time_sec`.
6. Group by `segment_id` → mean flow, mean speed, mean travel time; then v/c from mean_flow and capacity.
7. Return list of records for Pydantic.

---

### 3.5 `api/services/supabase_client.py`

Supabase REST client: segments (cached) and windowed observations.

**Purpose:** Read `road_segments` and `traffic_observations` from Supabase via PostgREST; cache segments in memory.

**Environment variables**

| Variable | Required | Description |
|----------|----------|-------------|
| `SUPABASE_URL` | Yes | Base URL (e.g. `https://xxxx.supabase.co`). |
| `SUPABASE_ANON_KEY` | Yes | Anon key for API auth. |

**Module state**

| Name | Type | Description |
|------|------|-------------|
| `_segments_cache` | `list[dict] \| None` | In-memory cache of full `road_segments` table; filled by `fetch_segments` or `warm_segment_cache`. |
| `_MAX_WINDOW_ROWS` | `int` | Max rows to request in one observations request (50_000). |

**Functions**

| Function | Purpose |
|----------|---------|
| `_get_headers()` | Returns headers with `apikey`, `Authorization`, `Accept` for PostgREST. |
| `_base_url()` | Returns `SUPABASE_URL` stripped. |
| `fetch_segments()` | GET `road_segments`; stores result in `_segments_cache` and returns it on subsequent calls. |
| `warm_segment_cache()` | Calls `fetch_segments()` (used at app startup). |
| `fetch_observations_window(start_iso, end_iso)` | GET `traffic_observations` with filters `timestamp>=start_iso` and `timestamp<end_iso`; returns list of dicts. |

**Supabase tables assumed**

- **road_segments:** at least `segment_id`, `geometry_wkt`, `length_m`, `road_class`, `lanes`, `free_flow_speed_kmh`, `capacity_vph`, `street_name`, etc.
- **traffic_observations:** at least `segment_id`, `timestamp`, `flow_vph` (speed/travel time are computed by the API via BPR, not stored).

---

### 3.6 `api/bpr.py`

BPR (Bureau of Public Roads) formula: flow → speed and travel time.

**Purpose:** Vectorized implementation so the API can compute speed and travel time for many observations without Python loops.

**Constants**

| Name | Value | Description |
|------|-------|-------------|
| `BPR_ALPHA` | 0.15 | BPR α. |
| `BPR_BETA` | 4.0 | BPR β. |

**Formula (conceptually)**

- Free-flow travel time: `t0 = length_km / free_flow_speed_kmh` (with unit conversion).
- Volume-to-capacity: `x = flow_vph / capacity_vph` (clipped 0–3).
- Travel time: `t = t0 * (1 + α * x^β)`.
- Speed: `speed_kmh = length_km / (t_sec / 3600)`.

**Function**

| Function | Purpose |
|----------|---------|
| `apply_bpr_vectorized(seg_idx, flow_vph, length_m, free_flow_speed_kmh, capacity_vph, alpha, beta)` | Takes 1D arrays (segment index per observation, flow, and per-segment length/speed/capacity); returns `(speed_kmh, travel_time_sec)` as 1D arrays same length as `flow_vph`. |

---

## 4. Data dictionary (API and dashboard)

### 4.1 Segment (road_segments / GET /segments)

| Field | Type | Description |
|-------|------|-------------|
| `segment_id` | string | Unique segment identifier. |
| `geometry_wkt` | string \| null | WKT LineString or MultiLineString. |
| `length_m` | number \| null | Segment length in meters. |
| `road_class` | string \| null | OSM road class (e.g. primary, residential). |
| `lanes` | int \| null | Number of lanes. |
| `free_flow_speed_kmh` | number \| null | Free-flow speed (km/h) for BPR. |
| `capacity_vph` | int \| null | Capacity in vehicles per hour. |
| `street_name` | string \| null | Display name. |
| `am_bias`, `pm_bias` | number \| null | Optional demand bias (if used in synthesis). |

### 4.2 Traffic observation (traffic_observations table)

| Field | Type | Description |
|-------|------|-------------|
| `segment_id` | string | Links to road_segments. |
| `timestamp` | ISO datetime | Time of the observation. |
| `flow_vph` | number | Observed flow (vehicles per hour). |

Speed and travel time are **not** stored; they are computed by the API using BPR from flow and segment attributes.

### 4.3 Traffic window row (GET /traffic/window response)

| Field | Type | Description |
|-------|------|-------------|
| `segment_id` | string | Segment ID. |
| `mean_flow_vph` | number | Mean flow in the window. |
| `mean_speed_kmh` | number \| null | Mean speed from BPR. |
| `mean_travel_time_sec` | number \| null | Mean travel time from BPR (seconds). |
| `vc_ratio` | number \| null | Volume-to-capacity (mean_flow_vph / capacity_vph), typically clipped. |

---

## 5. Environment variables summary

### 5.1 Dashboard (project root `.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `TRAFFIC_API_BASE_URL` | No | Base URL of the Traffic API (default in code if unset). |
| `OLLAMA_API_KEY` | Yes for AI summary | Ollama Cloud API key. |
| `OLLAMA_MODEL` | No | Model name (default `gpt-oss:20b-cloud`). |
| `OLLAMA_TIMEOUT` | No | Timeout in seconds (default 90). |

### 5.2 NewAPI (`.env` in NewAPI/ or repo root)

| Variable | Required | Description |
|----------|----------|-------------|
| `SUPABASE_URL` | Yes | Supabase project URL. |
| `SUPABASE_ANON_KEY` | Yes | Supabase anon/public key. |

---

## 6. File dependency summary

```text
app/app.py
  ← api_client (fetch_segments, fetch_traffic_window)
  ← llm_cloud (OllamaCloudError, query_llm)
  ← map_utils (build_map_data, vc_to_color, vc_severity_label, BAR_HARBOR_*, wkt_to_lonlat_path via build_map_data)

app/api_client.py
  ← httpx, pandas

app/llm_cloud.py
  ← os, httpx

app/map_utils.py
  ← numpy, pandas, shapely (optional for wkt)

NewAPI/api/main.py
  ← routers.traffic, services.supabase_client (warm_segment_cache)

NewAPI/api/routers/traffic.py
  ← schemas, services.supabase_client (fetch_segments), services.traffic_service (get_traffic_window)

NewAPI/api/services/traffic_service.py
  ← bpr (apply_bpr_vectorized), services.supabase_client (fetch_observations_window, fetch_segments)

NewAPI/api/services/supabase_client.py
  ← os, httpx
```

This codebook and the **README** together document how the pipeline is built, what each file and variable does, and what you need to run and use the data. For a screenshot-based walkthrough of dashboard features (Hourly vs Daily, map, KPIs, AI summary), see **App Functionality.md**. For the deployed app URL, see **App Link.md**.
