"""
Streamlit v1: traffic visualizations from road_segments.csv and traffic_observations.csv.
Shows driveable roads only by default. Run from repo root: streamlit run app/streamlit_app.py
"""

from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

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


@st.cache_data
def load_segments():
    return pd.read_csv(SEGMENTS_CSV)


@st.cache_data
def load_observations():
    df = pd.read_csv(OBSERVATIONS_CSV)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=False)
    return df


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


def main():
    st.set_page_config(page_title="Traffic dashboard", layout="wide")
    st.title("Traffic dashboard")
    st.caption("Default dataset: Bar Harbor (from data_pipeline/input/bar_harbor.osm). Driveable roads only by default.")

    if not SEGMENTS_CSV.exists() or not OBSERVATIONS_CSV.exists():
        st.error(f"CSV files not found in {OUTPUT_DIR}. Run the data pipeline first.")
        st.stop()

    segments = load_segments()
    observations = load_observations()

    # Sidebar controls
    with st.sidebar:
        driveable_only = st.checkbox(
            "Driveable roads only",
            value=True,
            help="Exclude footways, paths, tracks, cycleways, etc.",
        )
        st.markdown("### Congestion period")
        cong_mode = st.radio(
            "Display congestion for",
            ["All times", "Specific hour"],
            index=0,
            help="Use a specific hour-of-day to see peak vs off-peak congestion.",
        )
        cong_hour = None
        if cong_mode == "Specific hour":
            cong_hour = st.slider("Hour of day", 0, 23, 8)
        st.markdown("### Days included")
        day_filter = st.radio(
            "Include data from",
            ["All days", "Weekdays (Mon–Fri)", "Weekends (Sat–Sun)"],
            index=0,
        )
    if driveable_only:
        segments = segments[segments["road_class"].astype(str).str.lower().isin(DRIVEABLE)].copy()
        seg_ids = set(segments["segment_id"])
        observations = observations[observations["segment_id"].isin(seg_ids)].copy()

    # Optional day-of-week filter (applies to all downstream charts and congestion map)
    if day_filter != "All days":
        dow = observations["timestamp"].dt.dayofweek
        if day_filter.startswith("Weekdays"):
            observations = observations[dow < 5].copy()
        elif day_filter.startswith("Weekends"):
            observations = observations[dow >= 5].copy()

    if segments.empty:
        st.warning("No segments match the current filter.")
        st.stop()

    # One row of metrics
    n_seg = len(segments)
    n_obs = len(observations)
    t_min, t_max = observations["timestamp"].min(), observations["timestamp"].max()
    avg_flow = observations["flow_vph"].mean()
    avg_speed = observations["speed_kmh"].replace(0, pd.NA).mean()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Segments", f"{n_seg:,}")
    c2.metric("Time range", f"{t_min.date()} → {t_max.date()}")
    c3.metric("Avg flow (veh/h)", f"{avg_flow:.0f}")
    c4.metric("Avg speed (km/h)", f"{avg_speed:.1f}" if pd.notna(avg_speed) else "—")

    # Centre for maps: use first segment's geometry if available, else default
    map_center = [49.81, 6.42]
    for _, row in segments.head(1).iterrows():
        coords = wkt_to_latlon_pairs(row.get("geometry_wkt"))
        if coords:
            map_center = [coords[0][0], coords[0][1]]
            break

    # Congestion map: segments colored by v/c (mean flow / capacity) on a global scale for the current view
    st.subheader("Congestion map")
    seg_stats = observations.copy()
    if cong_hour is not None:
        seg_stats["hour"] = seg_stats["timestamp"].dt.hour
        seg_stats = seg_stats[seg_stats["hour"] == cong_hour]
    mean_flow_by_seg = seg_stats.groupby("segment_id").agg(mean_flow_vph=("flow_vph", "mean")).reset_index()
    segments_with_vc = segments.merge(mean_flow_by_seg, on="segment_id", how="left")
    segments_with_vc["mean_flow_vph"] = segments_with_vc["mean_flow_vph"].fillna(0.0)
    cap = segments_with_vc["capacity_vph"]
    segments_with_vc["vc_ratio"] = np.where(
        (cap > 0) & cap.notna(),
        segments_with_vc["mean_flow_vph"] / cap,
        np.nan,
    )

    # Show all (driveable) roads that are counted; use pydeck for performance.
    seg_for_congestion = segments_with_vc.copy()
    seg_for_congestion["path"] = seg_for_congestion["geometry_wkt"].map(wkt_to_lonlat_path)
    seg_for_congestion = seg_for_congestion[seg_for_congestion["path"].notna()].copy()

    # Use global v/c over the entire day (after day-of-week filter, before hour filter)
    # to define color bands, so off-peak hours naturally appear less congested.
    obs_cap = observations.merge(
        segments[["segment_id", "capacity_vph"]],
        on="segment_id",
        how="left",
    )
    obs_cap["vc_ratio_all"] = np.where(
        (obs_cap["capacity_vph"] > 0) & obs_cap["capacity_vph"].notna(),
        obs_cap["flow_vph"] / obs_cap["capacity_vph"],
        np.nan,
    )
    vc_vals = obs_cap["vc_ratio_all"].replace([np.inf, -np.inf], np.nan).dropna()
    if len(vc_vals) >= 8:
        q10, q30, q50, q65, q80, q90, q97 = np.quantile(
            vc_vals, [0.10, 0.30, 0.50, 0.65, 0.80, 0.90, 0.97]
        )
    elif len(vc_vals) > 0:
        vmax = vc_vals.max()
        q10, q30, q50, q65, q80, q90, q97 = (
            0.10 * vmax,
            0.30 * vmax,
            0.50 * vmax,
            0.65 * vmax,
            0.80 * vmax,
            0.90 * vmax,
            0.97 * vmax,
        )
    else:
        q10 = q30 = q50 = q65 = q80 = q90 = q97 = 0.0

    def congestion_color(vc):
        """Map global v/c to RGB using quantile bands for the current view."""
        if pd.isna(vc):
            return [180, 180, 180]  # gray
        v = vc
        if v < q10:
            return [0, 70, 0]       # very dark green (lowest flows)
        if v < q30:
            return [0, 120, 0]      # dark green
        if v < q50:
            return [0, 170, 0]      # green
        if v < q65:
            return [173, 255, 47]   # yellow‑green
        if v < q80:
            return [255, 215, 0]    # yellow
        if v < q90:
            return [255, 180, 0]    # yellow‑orange
        if v < q97:
            return [255, 140, 0]    # orange
        return [220, 20, 20]        # strong red (top few percent of v/c)

    seg_for_congestion["color"] = seg_for_congestion["vc_ratio"].map(congestion_color)

    st.caption(
        "Colors are based on global v/c for the current hour and day filter. Dark greens are the lowest flows in the "
        "city, yellows are moderate, and orange/red highlight the highest-flow corridors (top quantiles) across the city."
    )
    try:
        import pydeck as pdk
        layer = pdk.Layer(
            "PathLayer",
            data=seg_for_congestion,
            get_path="path",
            get_color="color",
            width_scale=10,
            width_min_pixels=1,
            get_width=2,
            pickable=True,
        )
        view_state = pdk.ViewState(
            latitude=map_center[0],
            longitude=map_center[1],
            zoom=13.5,
        )
        tooltip = {
            "text": "name={street_name}\nseg={segment_id}\nclass={road_class}\nv/c={vc_ratio:.2f}\nmean_flow={mean_flow_vph:.0f}"
        }
        deck = pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip=tooltip)
        st.pydeck_chart(deck, width="stretch", height=420)
    except Exception:
        st.warning("pydeck failed to render the congestion map. (Streamlit includes pydeck by default.)")

    # Single time series: flow and speed on one chart (two lines)
    st.subheader("Traffic over time")
    agg = observations.groupby("timestamp").agg(flow_vph=("flow_vph", "mean"), speed_kmh=("speed_kmh", "mean")).reset_index()
    agg["speed_kmh"] = agg["speed_kmh"].replace(0, pd.NA)

    try:
        import plotly.express as px
        import plotly.graph_objects as go
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=agg["timestamp"], y=agg["flow_vph"], name="Flow (veh/h)", yaxis="y"))
        fig.add_trace(go.Scatter(x=agg["timestamp"], y=agg["speed_kmh"], name="Speed (km/h)", yaxis="y2"))
        fig.update_layout(
            height=300,
            margin=dict(l=20, r=20, t=20, b=20),
            yaxis=dict(title="Flow (veh/h)"),
            yaxis2=dict(title="Speed (km/h)", overlaying="y", side="right"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig, width="stretch")
    except ImportError:
        st.line_chart(agg.set_index("timestamp")[["flow_vph", "speed_kmh"]])

    # Segment ranking (prioritization): top N by flow × length
    st.subheader("Segment ranking (prioritization)")
    mean_flow = observations.groupby("segment_id")["flow_vph"].mean().reset_index()
    mean_flow.columns = ["segment_id", "mean_flow_vph"]
    ranking = segments.merge(mean_flow, on="segment_id", how="left")
    ranking["mean_flow_vph"] = ranking["mean_flow_vph"].fillna(0)
    ranking["score"] = ranking["mean_flow_vph"] * ranking["length_m"]
    ranking = ranking.sort_values("score", ascending=False).head(30).reset_index(drop=True)
    ranking["rank"] = range(1, len(ranking) + 1)
    display_rank = ranking[["rank", "segment_id", "street_name", "road_class", "length_m", "mean_flow_vph", "score"]].copy()
    display_rank["length_m"] = display_rank["length_m"].round(1)
    display_rank["mean_flow_vph"] = display_rank["mean_flow_vph"].round(0)
    display_rank["score"] = display_rank["score"].round(0)
    st.caption("Top segments by flow × length (vehicle-miles proxy). Use for investment or congestion focus.")
    st.dataframe(display_rank, width="stretch", hide_index=True)

    # Hourly profile: mean flow and speed by hour of day
    st.subheader("Hourly profile")
    obs_hour = observations.copy()
    obs_hour["hour"] = obs_hour["timestamp"].dt.hour
    obs_hour["speed_kmh"] = obs_hour["speed_kmh"].replace(0, pd.NA)
    hourly = obs_hour.groupby("hour").agg(flow_vph=("flow_vph", "mean"), speed_kmh=("speed_kmh", "mean")).reset_index()
    hourly = hourly.set_index("hour").reindex(range(24)).reset_index()
    hourly["flow_vph"] = hourly["flow_vph"].fillna(0)
    try:
        import plotly.graph_objects as go
        fig_h = go.Figure()
        fig_h.add_trace(go.Scatter(x=hourly["hour"], y=hourly["flow_vph"], name="Flow (veh/h)", yaxis="y"))
        fig_h.add_trace(go.Scatter(x=hourly["hour"], y=hourly["speed_kmh"], name="Speed (km/h)", yaxis="y2"))
        fig_h.update_layout(
            height=300,
            margin=dict(l=20, r=20, t=20, b=20),
            xaxis=dict(title="Hour of day"),
            yaxis=dict(title="Mean flow (veh/h)"),
            yaxis2=dict(title="Mean speed (km/h)", overlaying="y", side="right"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig_h, width="stretch")
    except ImportError:
        st.line_chart(hourly.set_index("hour")[["flow_vph", "speed_kmh"]])

    # One bar chart: segments by road class
    st.subheader("Segments by road class")
    by_class = segments.groupby("road_class").agg(n=("segment_id", "count")).reset_index().sort_values("n", ascending=False)
    try:
        import plotly.express as px
        fig = px.bar(by_class, x="road_class", y="n", title="")
        fig.update_layout(height=280, margin=dict(l=20, r=20, t=20, b=80), xaxis_tickangle=-45, showlegend=False)
        st.plotly_chart(fig, width="stretch")
    except ImportError:
        st.bar_chart(by_class.set_index("road_class"))


if __name__ == "__main__":
    main()
