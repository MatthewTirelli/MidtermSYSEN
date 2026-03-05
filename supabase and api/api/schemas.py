"""
Pydantic models for Bar Harbor Traffic Report API responses.
"""

from pydantic import BaseModel


class RoadSegment(BaseModel):
    """Road segment from Supabase road_segments table."""

    segment_id: str
    geometry_wkt: str | None = None
    length_m: float | None = None
    road_class: str | None = None
    lanes: int | None = None
    free_flow_speed_kmh: float | None = None
    capacity_vph: int | None = None
    am_bias: float | None = None
    pm_bias: float | None = None
    street_name: str | None = None

    class Config:
        from_attributes = True


class TrafficObservation(BaseModel):
    """Traffic observation with BPR-derived speed and travel time (from GET /observations)."""

    segment_id: str
    timestamp: str
    flow_vph: float
    speed_kmh: float | None = None
    travel_time_sec: float | None = None

    class Config:
        from_attributes = True
