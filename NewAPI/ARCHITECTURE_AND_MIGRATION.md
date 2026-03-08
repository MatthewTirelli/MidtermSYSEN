# Traffic API Redesign: Architecture & Migration

## PART 1 — What's Wrong and Why Redesign

### Current architecture problems

1. **Wrong abstraction**  
   The API exposes a single "dump" endpoint (`GET /observations`) that returns raw (segment_id, timestamp, flow_vph, speed_kmh, travel_time_sec) rows. The app never needs that raw table; it needs **segment-level metrics for a time window** (e.g. mean flow per segment to color a map and compute v/c).

2. **Expensive fetch + compute**  
   Every request pulls all matching rows from Supabase (up to 30k–100k), transfers them, then applies BPR in Python and serializes a huge JSON array. That causes slow response times, high memory use, and unnecessary network payload.

3. **Redundant work**  
   The app immediately aggregates observations by segment (`groupby("segment_id").agg(mean_flow_vph=...)`). Doing that aggregation in the API would cut payload size and client work and would match how the app actually uses the data.

4. **No analytics-oriented API**  
   There is no endpoint that answers "traffic for this city and time window" in a compact, analytics-ready shape. The system is built around table dumps, not use cases.

### Why the old `/observations` endpoint is a bad fit

- Returns **O(observations)** rows (often tens of thousands) when the app only needs **O(segments)** (hundreds).
- Forces the client to do aggregation, parsing, and quantile logic that belongs in the backend.
- Encourages unbounded or large `limit` values, which make responses slow and brittle.
- Does not scale when observation volume grows (e.g. more segments or finer time resolution).

---

## PART 2 — New API Design

The new API is organized around **what the app needs**: segment metadata, traffic for a time window (per-segment and summary), and optional hourly/raw access.

| Endpoint | Purpose | App use |
|----------|---------|---------|
| **GET /segments** | Static road segment metadata (geometry, class, capacity, etc.) | Baseline map; merge with traffic for coloring |
| **GET /traffic/window** | One row per segment for a time window: mean flow, mean speed, count, v/c | **Primary**: replace `load_observations` + client-side groupby for map coloring |
| **GET /traffic/summary** | Compact stats for a window: counts, averages, optional quantiles | Metrics panel, color-scale quantiles |
| **GET /traffic/hourly** | One row per segment per hour for a date/range | Time-series or hourly heatmaps |
| **GET /traffic/raw** | Raw observations with strict limit and pagination | Debug or special cases only |
| **GET /observations** (legacy) | Same as before, deprecated | Temporary compatibility; migrate to `/traffic/window` + `/traffic/summary` |

### Request parameters (shared where applicable)

- **date** (YYYY-MM-DD): calendar day
- **start_hour**, **end_hour** (0–23): hour window; if end ≤ start, next day is assumed
- **segment_ids**: optional filter (comma-separated or repeated)
- **max_rows** / **limit**: safe caps on returned rows (validated and bounded)

### Response shape (compact, app-friendly)

- **/traffic/window**: list of `{ segment_id, mean_flow_vph, mean_speed_kmh, mean_travel_time_sec, observation_count, vc_ratio }`
- **/traffic/summary**: `{ total_observations, segment_count, avg_flow_vph, avg_speed_kmh, vc_quantiles? }`
- **/traffic/hourly**: list of `{ segment_id, hour_iso, mean_flow_vph, mean_speed_kmh, observation_count }`
- **/traffic/raw**: same as legacy observation rows, with strict limit and optional offset

---

## PART 3 — Backward Compatibility and Migration Plan

### What stays

- **GET /segments**  
  Unchanged path and response. The app continues to call it as today.

- **GET /observations** (legacy)  
  Kept temporarily with the **same** query parameters and response fields (segment_id, timestamp, flow_vph, speed_kmh, travel_time_sec). It is marked **deprecated** in OpenAPI and should call the same service layer (bounded fetch + vectorized BPR) so behavior stays correct while we migrate the app.

### Migration strategy

1. **Deploy the new API**  
   New endpoints live alongside the old ones. No breaking changes yet.

2. **Update the app in two steps**  
   - **Step A (recommended first):**  
     - Keep using `GET /segments` as-is.  
     - Replace the single "load observations" call with two calls:  
       - `GET /traffic/window?date=...&start_hour=...&end_hour=...` → per-segment metrics for the map.  
       - `GET /traffic/summary?date=...&start_hour=...&end_hour=...` → total_observations, avg_flow_vph, avg_speed_kmh, and optional vc_quantiles for the legend/metrics.  
     - In the app, stop calling `load_observations()` (or equivalent) for the map; instead build the map from segments + window response and use summary for metrics and quantiles.  
   - **Step B:**  
     - Remove or hide the legacy `GET /observations` path from the app.  
     - Rely only on `/segments`, `/traffic/window`, and `/traffic/summary` (and `/traffic/hourly` if you add hourly views).

3. **Deprecate then remove legacy**  
   - Document `GET /observations` as deprecated and point clients to `/traffic/window` and `/traffic/summary`.  
   - After all clients migrate, remove the legacy endpoint or keep it behind a feature flag with a strict row limit.

### Which app calls to change

| Current | New | Notes |
|--------|-----|------|
| `GET /segments` | Keep | No change |
| `GET /observations?limit=10000&date=...&start_hour=...&end_hour=...` | `GET /traffic/window?date=...&start_hour=...&end_hour=...` | Primary: per-segment metrics for map |
| (same) | `GET /traffic/summary?date=...&start_hour=...&end_hour=...` | Counts, averages, quantiles for metrics/legend |
| (none) | `GET /traffic/hourly?date=...` (optional) | Only if you add hourly views |

### App code changes (high level)

- **load_observations(...)**  
  Replace with something like `load_traffic_window(api_base, date, start_hour, end_hour)` that:
  - Calls `GET /traffic/window` and returns a DataFrame with one row per segment (segment_id, mean_flow_vph, mean_speed_kmh, observation_count, vc_ratio).
  - Optionally calls `GET /traffic/summary` for total_observations, avg_flow_vph, avg_speed_kmh, and vc_quantiles.
- **Map coloring**  
  Use the window response: merge `mean_flow_vph` (and capacity from segments) to get v/c per segment; use summary's vc_quantiles for the color scale if the API returns them.
- **Metrics panel**  
  Use summary response: total_observations, segment_count, avg_flow_vph, avg_speed_kmh.

This keeps a **safe migration path**: old endpoint remains until the app is updated, then you can deprecate and later remove it.

---

## PART 4 — App integration (concrete steps)

### Replace `load_observations` with window + summary

**Current (app):**  
`load_observations(api_base, limit=10_000, date=..., start_hour=..., end_hour=...)`  
→ single GET /observations, then client-side `groupby("segment_id").agg(mean_flow_vph=...)` and quantiles.

**New (app):**

1. **For the map (per-segment metrics):**  
   - Call `GET /traffic/window?date=YYYY-MM-DD&start_hour=H&end_hour=H`.  
   - Response is one row per segment: `segment_id`, `mean_flow_vph`, `mean_speed_kmh`, `observation_count`, `vc_ratio`.  
   - Build a DataFrame from this and merge with segments on `segment_id`. Use `mean_flow_vph` and segment `capacity_vph` (or the API's `vc_ratio`) for map coloring.

2. **For metrics and quantiles:**  
   - Call `GET /traffic/summary?date=...&start_hour=...&end_hour=...`.  
   - Use `total_observations`, `segment_count`, `avg_flow_vph`, `avg_speed_kmh` for the metrics panel.  
   - Use `vc_quantiles` (q10, q30, q50, …) for the congestion color scale instead of computing quantiles from raw observations.

### Suggested app function

```python
@st.cache_data
def load_traffic_window(api_base: str, date: str, start_hour: int, end_hour: int):
    """Returns (window_df, summary_dict, error_str)."""
    base = api_base.rstrip("/")
    # Per-segment metrics for map
    r1 = httpx.get(f"{base}/traffic/window", params={"date": date, "start_hour": start_hour, "end_hour": end_hour}, timeout=60.0)
    if r1.status_code != 200:
        return None, None, r1.text
    window_df = pd.DataFrame(r1.json())
    # Summary + quantiles for metrics and color scale
    r2 = httpx.get(f"{base}/traffic/summary", params={"date": date, "start_hour": start_hour, "end_hour": end_hour}, timeout=60.0)
    if r2.status_code != 200:
        return window_df, None, r2.text
    summary = r2.json()
    return window_df, summary, None
```

### Map coloring

- Merge `window_df` with segments on `segment_id`.  
- Use `vc_ratio` from the window response directly, or compute `mean_flow_vph / capacity_vph` from segments.  
- Use `summary["vc_quantiles"]` (q10, q30, q50, q65, q80, q90, q97) for the same congestion color buckets the app uses today.

### What to remove in the app

- Remove or stop using `load_observations()` for the main map/summary flow.  
- Remove client-side `groupby("segment_id").agg(...)` and quantile computation from raw observations.  
- Keep `load_segments()` unchanged; keep using GET /segments.

---

## Stretch / future

- **BPR in SQL:** Move BPR into a Supabase view or RPC so aggregation can be done server-side.  
- **Materialized views:** Pre-aggregate by (date, hour, segment_id) for very fast window/summary.  
- **Redis cache:** Replace in-process segment cache for multi-instance deployments.  
- **Pagination / streaming:** For /traffic/raw or large hourly results, add offset/limit or streaming.  
- **Benchmarking:** Use `locust` or `pytest-benchmark` against GET /traffic/window and GET /traffic/summary vs legacy /observations to document speedup.
