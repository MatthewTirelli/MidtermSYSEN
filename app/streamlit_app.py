"""
Bar Harbor Traffic: baseline map first, then load traffic for a chosen time window.
Calls the Bar Harbor Traffic Report API (GET /segments, GET /observations).
Run from repo root: streamlit run app/streamlit_app.py
"""

import logging
import os
from datetime import date as date_type
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import streamlit as st

# Bar Harbor, ME approximate center (lat, lon)
BAR_HARBOR_CENTER = [44.39, -68.21]

# Roads that typically allow cars (excludes footway, path, track, cycleway, etc.)
DRIVEABLE = {
    "motorway", "trunk", "primary", "secondary", "tertiary",
    "residential", "unclassified", "service", "living_street",
    "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link",
}

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "data_pipeline" / "output"
SEGMENTS_CSV = OUTPUT_DIR / "road_segments.csv"
OBSERVATIONS_CSV = OUTPUT_DIR / "traffic_observations.csv"

# Default API base URL when using "Load from API".
# Deployed Bar Harbor Traffic Report on Posit Connect; override with TRAFFIC_API_BASE_URL for local.
DEFAULT_API_BASE = os.environ.get(
    "TRAFFIC_API_BASE_URL",
    "https://connect.systems-apps.com/content/4579a545-541d-412e-93d4-b35ef9cbca66",
)


def _fetch_from_api(base_url: str, path: str, params: Optional[dict] = None):
    """GET JSON from API. Returns (data, None) on success, (None, error_message) on failure."""
    logger = logging.getLogger("bar_harbor_traffic")
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    logger.info("API GET %s params=%s", url, params)
    try:
        import httpx
        r = httpx.get(url, params=params, timeout=120.0)
        r.raise_for_status()
        data = r.json()
        logger.info("API %s success, %s items", path, len(data) if isinstance(data, list) else "?")
        return data, None
    except httpx.ConnectError as e:
        logger.error("API connect error: %s", e)
        return None, f"Could not connect: {e}"
    except httpx.TimeoutException as e:
        logger.error("API timeout: %s", e)
        return None, f"Request timed out: {e}"
    except httpx.HTTPStatusError as e:
        msg = f"API returned {e.response.status_code}: {e.response.text[:200] if e.response.text else ''}"
        logger.error("API HTTP error: %s", msg)
        return None, msg
    except Exception as e:
        logger.exception("API error: %s", e)
        return None, str(e)


@st.cache_data
def load_segments(api_base: Optional[str] = None):
    """Load segments from API (if api_base set) or from local CSV. Returns (df, error_str or None)."""
    if api_base:
        data, err = _fetch_from_api(api_base, "segments")
        if err:
            return None, err
        if data is not None:
            return pd.DataFrame(data), None
        return None, "No data from /segments"
    try:
        return pd.read_csv(SEGMENTS_CSV), None
    except Exception as e:
        return None, str(e)


def _apply_bpr(observations: pd.DataFrame, segments: pd.DataFrame, alpha: float = 0.15, beta: float = 4.0) -> pd.DataFrame:
    """BPR: t = t0 * (1 + alpha * (v/c)^beta). Adds speed_kmh and travel_time_sec to observations."""
    seg = segments.set_index("segment_id")
    t0_sec = (seg["length_m"] / 1000) / (seg["free_flow_speed_kmh"] / 3600)
    cap = seg["capacity_vph"]
    length_m = seg["length_m"]
    out = observations.copy()
    speed_kmh = []
    travel_time_sec = []
    for _, row in observations.iterrows():
        seg_id = row["segment_id"]
        v, c = row["flow_vph"], cap.loc[seg_id]
        t0 = t0_sec.loc[seg_id]
        ratio = min(v / c, 3.0) if c > 0 else 0.0
        t_sec = t0 * (1 + alpha * (ratio**beta))
        if np.isfinite(t_sec) and t_sec > 0:
            speed_kmh.append((length_m.loc[seg_id] / 1000) / (t_sec / 3600))
            travel_time_sec.append(t_sec)
        else:
            speed_kmh.append(np.nan)
            travel_time_sec.append(np.nan)
    out["speed_kmh"] = np.round(speed_kmh, 2)
    out["travel_time_sec"] = np.round(travel_time_sec, 2)
    return out


@st.cache_data
def load_observations(
    api_base: Optional[str] = None,
    limit: Optional[int] = 10_000,
    date: Optional[str] = None,
    start_hour: Optional[int] = None,
    end_hour: Optional[int] = None,
):
    """Load observations from API (if api_base set) or from local CSV. API returns BPR fields already.
    When date + start_hour + end_hour are set, only that time window is requested (e.g. 6-7pm).
    """
    if api_base:
        params = {}
        if limit is not None:
            params["limit"] = limit
        if date:
            params["date"] = date
        if start_hour is not None and end_hour is not None:
            params["start_hour"] = start_hour
            params["end_hour"] = end_hour
        data, err = _fetch_from_api(api_base, "observations", params=params if params else None)
        if err:
            return None, err
        if data is not None:
            df = pd.DataFrame(data)
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=False)
            return df, None
        return None, "No data from /observations"
    if not OBSERVATIONS_CSV.exists():
        return None, "CSV not found"
    try:
        df = pd.read_csv(OBSERVATIONS_CSV)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=False)
        if "speed_kmh" not in df.columns:
            segments, _ = load_segments(api_base=None)
            if segments is not None:
                df = _apply_bpr(df, segments)
        return df, None
    except Exception as e:
        return None, str(e)


def wkt_to_latlon_pairs(wkt_str):
    if pd.isna(wkt_str) or not str(wkt_str).strip().upper().startswith("LINESTRING"):
        return None
    try:
        from shapely import wkt as wkt_load
        g = wkt_load.loads(wkt_str)
        if g is None or g.is_empty:
            return None
        coords = list(zip(g.xy[1], g.xy[0]))
        return coords if len(coords) >= 2 else None
    except Exception:
        return None


def wkt_to_lonlat_path(wkt_str):
    """Parse WKT LineString/MultiLineString to a pydeck PathLayer path: list[[lon,lat], ...]."""
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
            xs, ys = g.xy  # lon, lat
            return [[float(x), float(y)] for x, y in zip(xs, ys)]
        if g.geom_type == "MultiLineString":
            paths = []
            for part in g.geoms:
                xs, ys = part.xy
                paths.extend([[float(x), float(y)] for x, y in zip(xs, ys)])
            return paths if len(paths) >= 2 else None
    except Exception:
        return None
    return None


def _setup_logging():
    """Configure logging and in-memory buffer for UI."""
    if "log_buffer" not in st.session_state:
        st.session_state["log_buffer"] = []

    class BufferHandler(logging.Handler):
        def emit(self, record):
            st.session_state["log_buffer"].append(self.format(record))
            if len(st.session_state["log_buffer"]) > 100:
                st.session_state["log_buffer"] = st.session_state["log_buffer"][-100:]

    log = logging.getLogger("bar_harbor_traffic")
    if not log.handlers:
        log.setLevel(logging.DEBUG)
        h = BufferHandler()
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(h)
    return log


def main():
    st.set_page_config(page_title="Bar Harbor Traffic", layout="wide")
    log = _setup_logging()

    st.title("Bar Harbor Traffic")
    st.caption("Pick a date and time range, then click **Show traffic for this time** to load congestion for that window.")

    # Session state for traffic data (phase 2)
    if "traffic_obs" not in st.session_state:
        st.session_state["traffic_obs"] = None
    if "traffic_err" not in st.session_state:
        st.session_state["traffic_err"] = None
    if "traffic_params" not in st.session_state:
        st.session_state["traffic_params"] = None

    # Sidebar: API only (plan: baseline map from API, traffic on demand)
    with st.sidebar:
        st.markdown("### Bar Harbor Traffic API")
        api_base = st.text_input(
            "API base URL",
            value=DEFAULT_API_BASE,
            help="Bar Harbor Traffic Report API (GET /segments, GET /observations).",
        ).strip() or None
        if not api_base:
            st.warning("Enter the API base URL.")
            st.stop()

        st.markdown("### Time window")
        selected_date = st.date_input("Date", value=date_type(2025, 3, 3))
        start_hour = st.selectbox("Start hour", range(24), index=18, format_func=lambda h: f"{h}:00")
        end_hour = st.selectbox("End hour", range(24), index=19, format_func=lambda h: f"{h}:00")
        day_name = selected_date.strftime("%A")
        st.caption(f"Day: **{day_name}**")

        show_traffic_clicked = st.button("Show traffic for this time", type="primary")
        driveable_only = st.checkbox("Driveable roads only", value=True, help="Exclude footways, paths, etc.")
        if st.button("Clear cache"):
            st.cache_data.clear()
            st.session_state["traffic_obs"] = None
            st.session_state["traffic_err"] = None
            st.session_state["traffic_params"] = None
            st.rerun()
        st.markdown("---")

    # Phase 1: Load segments only (baseline map)
    log.info("Fetching segments from API")
    segments, seg_err = load_segments(api_base=api_base)
    if segments is None or segments.empty:
        err_msg = seg_err or "Could not load road segments."
        log.error(err_msg)
        st.error("Could not load road network. " + err_msg)
        with st.expander("Error details / logs"):
            st.text("\n".join(st.session_state.get("log_buffer", [])[-30:]))
        st.stop()
    log.info("Segments loaded: %s", len(segments))

    n_segments_loaded = len(segments)
    if driveable_only:
        segments = segments[segments["road_class"].astype(str).str.lower().isin(DRIVEABLE)].copy()
    if segments.empty:
        st.warning("No driveable segments.")
        st.stop()

    # Map center: Bar Harbor default, or from first segment
    map_center = list(BAR_HARBOR_CENTER)
    for _, row in segments.head(1).iterrows():
        coords = wkt_to_latlon_pairs(row.get("geometry_wkt"))
        if coords:
            map_center = [coords[0][0], coords[0][1]]
            break

    # Fetch observations when user clicks "Show traffic"
    obs_date = selected_date.strftime("%Y-%m-%d")
    if show_traffic_clicked:
        log.info("Fetching observations: date=%s %s-%s", obs_date, start_hour, end_hour)
        observations, obs_err = load_observations(
            api_base=api_base,
            limit=10_000,
            date=obs_date,
            start_hour=start_hour,
            end_hour=end_hour,
        )
        st.session_state["traffic_obs"] = observations
        st.session_state["traffic_err"] = obs_err
        st.session_state["traffic_params"] = (obs_date, start_hour, end_hour)
        if obs_err:
            log.error("Observations error: %s", obs_err)
        elif observations is not None and not observations.empty:
            log.info("Observations loaded: %s rows", len(observations))
        st.rerun()

    observations = st.session_state["traffic_obs"]
    traffic_params = st.session_state["traffic_params"]
    traffic_err = st.session_state["traffic_err"]

    # Baseline map (gray) or traffic overlay (colored by v/c)
    seg_for_map = segments.copy()
    seg_for_map["path"] = seg_for_map["geometry_wkt"].map(wkt_to_lonlat_path)
    seg_for_map = seg_for_map[seg_for_map["path"].notna()].copy()

    if observations is not None and not observations.empty and traffic_params == (obs_date, start_hour, end_hour):
        # Color by v/c for this window only
        seg_stats = observations.groupby("segment_id").agg(mean_flow_vph=("flow_vph", "mean")).reset_index()
        seg_for_map = seg_for_map.merge(seg_stats, on="segment_id", how="left")
        seg_for_map["mean_flow_vph"] = seg_for_map["mean_flow_vph"].fillna(0.0)
        cap = seg_for_map["capacity_vph"]
        seg_for_map["vc_ratio"] = np.where(
            (cap > 0) & cap.notna(),
            seg_for_map["mean_flow_vph"] / cap,
            np.nan,
        )
        obs_cap = observations.merge(segments[["segment_id", "capacity_vph"]], on="segment_id", how="left")
        obs_cap["vc_ratio_all"] = np.where(
            (obs_cap["capacity_vph"] > 0) & obs_cap["capacity_vph"].notna(),
            obs_cap["flow_vph"] / obs_cap["capacity_vph"],
            np.nan,
        )
        vc_vals = obs_cap["vc_ratio_all"].replace([np.inf, -np.inf], np.nan).dropna()
        if len(vc_vals) >= 8:
            q10, q30, q50, q65, q80, q90, q97 = np.quantile(vc_vals, [0.10, 0.30, 0.50, 0.65, 0.80, 0.90, 0.97])
        elif len(vc_vals) > 0:
            vmax = vc_vals.max()
            q10, q30, q50, q65, q80, q90, q97 = 0.10 * vmax, 0.30 * vmax, 0.50 * vmax, 0.65 * vmax, 0.80 * vmax, 0.90 * vmax, 0.97 * vmax
        else:
            q10 = q30 = q50 = q65 = q80 = q90 = q97 = 0.0

        def congestion_color(vc):
            if pd.isna(vc):
                return [180, 180, 180]
            if vc < q10:
                return [0, 70, 0]
            if vc < q30:
                return [0, 120, 0]
            if vc < q50:
                return [0, 170, 0]
            if vc < q65:
                return [173, 255, 47]
            if vc < q80:
                return [255, 215, 0]
            if vc < q90:
                return [255, 180, 0]
            if vc < q97:
                return [255, 140, 0]
            return [220, 20, 20]

        seg_for_map["color"] = seg_for_map["vc_ratio"].map(congestion_color)
        map_title = "Traffic (congestion) map"
        map_caption = f"Window: {day_name} {obs_date} {start_hour}:00–{end_hour}:00. Green = low congestion, red = high."
    else:
        seg_for_map["color"] = [[180, 180, 180]] * len(seg_for_map)
        map_title = "Bar Harbor road network (baseline)"
        map_caption = "Pick a date and time range, then click **Show traffic for this time** to load congestion."
        if traffic_err:
            st.error("Could not load traffic. " + traffic_err)

    st.subheader(map_title)
    st.caption(map_caption)

    # Legend (when showing traffic)
    if observations is not None and not observations.empty and traffic_params == (obs_date, start_hour, end_hour):
        st.markdown(
            "**Legend:** Low congestion (green) → High congestion (red)  |  "
            "Gray = no data for this segment in the selected window."
        )

    try:
        import pydeck as pdk
        layer = pdk.Layer(
            "PathLayer",
            data=seg_for_map,
            get_path="path",
            get_color="color",
            width_scale=10,
            width_min_pixels=1,
            get_width=2,
            pickable=True,
        )
        view_state = pdk.ViewState(latitude=map_center[0], longitude=map_center[1], zoom=13.5)
        tooltip = {"text": "name={street_name}\nseg={segment_id}\nclass={road_class}\nv/c={vc_ratio:.2f}\nmean_flow={mean_flow_vph:.0f}"} if "vc_ratio" in seg_for_map.columns else {"text": "name={street_name}\nseg={segment_id}\nclass={road_class}"}
        deck = pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip=tooltip)
        st.pydeck_chart(deck, height=420)
    except Exception as e:
        log.exception("pydeck failed")
        st.warning("Map could not be rendered. " + str(e))

    # Summary metrics when traffic is loaded
    if observations is not None and not observations.empty and traffic_params == (obs_date, start_hour, end_hour):
        n_obs = len(observations)
        avg_flow = observations["flow_vph"].mean()
        avg_speed = observations["speed_kmh"].replace(0, pd.NA).mean()
        st.metric("Segments shown", f"{len(seg_for_map):,}")
        st.metric("Observations in window", f"{n_obs:,}")
        st.metric("Avg flow (veh/h)", f"{avg_flow:.0f}")
        st.metric("Avg speed (km/h)", f"{avg_speed:.1f}" if pd.notna(avg_speed) else "—")

    # Error details / logs expander
    with st.expander("Error details / logs"):
        if traffic_err:
            st.error(traffic_err)
        st.text("\n".join(st.session_state.get("log_buffer", [])[-30:]))


if __name__ == "__main__":
    main()
