from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class JobResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "failed"]
    created_at: datetime
    updated_at: datetime
    progress_percent: float | None = None
    message: str | None = None
    output_file_path: str | None = None
    error: str | None = None


class DashboardTrackPoint(BaseModel):
    latitude: float
    longitude: float
    timestamp: datetime | None = None


class DashboardSessionOverview(BaseModel):
    id: str
    boat_id: str | None
    boat_name: str | None
    name: str
    location: str | None = None
    start_at: datetime | None
    end_at: datetime | None
    duration_hours: float
    distance_nm: float
    max_speed_kts: float | None
    foiling_time_min: float | None
    foiling_percentage: float | None
    tack_count: float | None = None
    gybe_count: float | None = None
    foiling_tack_count: float | None = None
    foiling_gybe_count: float | None = None
    foiling_tack_percentage: float | None = None
    foiling_gybe_percentage: float | None = None
    wind_speed_kts: float | None
    wind_gust_kts: float | None
    wind_direction_deg: float | None
    wave_height_m: float | None = None
    manual_wind_speed_kts: float | None = None
    manual_wind_gust_kts: float | None = None
    manual_wind_direction_deg: float | None = None
    manual_wave_height_m: float | None = None
    external_wind_speed_kts: float | None = None
    external_wind_gust_kts: float | None = None
    external_wind_direction_deg: float | None = None
    notes: str | None = None
    track_points: list[DashboardTrackPoint] = Field(default_factory=list)


class DashboardBoatOverview(BaseModel):
    id: str
    name: str
    class_name: str | None
    sailnumber: str | None = None
    session_count: int
    total_hours: float
    total_distance_nm: float
    max_speed_kts: float | None


class BoatWriteRequest(BaseModel):
    name: str
    class_name: str
    sailnumber: str


class BoatResponse(BaseModel):
    id: str
    name: str
    class_name: str
    sailnumber: str


class DashboardOverviewResponse(BaseModel):
    boat_count: int
    session_count: int
    total_hours: float
    total_distance_nm: float
    boats: list[DashboardBoatOverview]
    sessions: list[DashboardSessionOverview]


class SessionDataValue(BaseModel):
    timestamp: datetime
    value: float | bool | str


class SessionDataChannel(BaseModel):
    id: str
    name: str
    unit: str | None
    source: str | None
    is_derived: bool
    data_type: Literal["real", "boolean", "string"]
    values: list[SessionDataValue] = Field(default_factory=list)


class SessionDataMetric(BaseModel):
    id: str
    name: str
    value: float | None
    unit: str
    source: str


class SessionDataEvent(BaseModel):
    id: str
    event_type: str
    start_time: datetime | None
    end_time: datetime | None
    source: str
    confidence: float | None
    foiling: bool = False
    latitude: float | None = None
    longitude: float | None = None


class SessionDataProvenanceRecord(BaseModel):
    id: str
    producer: str
    produced_type: str
    produced_name: str
    action: str


class SessionDataSession(BaseModel):
    id: str
    name: str
    start_at: datetime | None
    end_at: datetime | None
    boat_id: str | None
    boat_name: str | None
    source: str | None
    wind_speed_kts: float | None
    wind_gust_kts: float | None
    wind_direction_deg: float | None
    wave_height_m: float | None = None
    notes: str | None = None


class SessionRace(BaseModel):
    id: str
    session_id: str
    name: str
    start_time: datetime
    finish_time: datetime


class SessionDataResponse(BaseModel):
    session: SessionDataSession
    channels: list[SessionDataChannel]
    metrics: list[SessionDataMetric]
    events: list[SessionDataEvent]
    provenance: list[SessionDataProvenanceRecord]
    races: list[SessionRace] = Field(default_factory=list)


class SessionWriteRequest(BaseModel):
    name: str
    location: str
    notes: str | None = None


class SessionResponse(BaseModel):
    id: str
    name: str
    location: str | None = None
    notes: str | None = None


class SessionNotesUpdateRequest(BaseModel):
    notes: str | None = None


class SessionNotesUpdateResponse(BaseModel):
    session_id: str
    notes: str | None = None


class SessionManualWindDirectionUpdateRequest(BaseModel):
    manual_wind_direction_deg: float | None = None


class SessionManualWindDirectionUpdateResponse(BaseModel):
    session_id: str
    manual_wind_direction_deg: float | None = None


VideoOverlayPosition = Literal["top", "bottom", "left", "right"]


class SessionVideoTriggerRequest(BaseModel):
    file_path: str
    output_folder: str | None = None
    sog_channel: str | None = None
    channel_names: list[str] = Field(default_factory=list)
    overlay_position: VideoOverlayPosition = "bottom"
    overlay_layout: dict[VideoOverlayPosition, list[str]] = Field(default_factory=dict)


class SessionVideoTriggerResponse(BaseModel):
    session_id: str
    file_path: str
    output_file_path: str | None = None
    status: Literal["accepted", "completed"]


class SessionRaceCreateRequest(BaseModel):
    name: str
    start_time: datetime
    finish_time: datetime
