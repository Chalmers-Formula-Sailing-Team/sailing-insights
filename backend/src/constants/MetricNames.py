from enum import Enum


class MetricNames(Enum):
    MANUAL_WIND_SPEED = "manual_wind_speed_kn"
    MANUAL_WIND_GUST = "manual_wind_gust_kn"
    MANUAL_WIND_DIRECTION = "manual_wind_direction_deg"
    MANUAL_WAVE_HEIGHT = "manual_wave_height_m"
    MANUAL_WIND_SOURCE = "upload_metadata"
    FOILING_TIME = "foiling_time_min"
    FOILING_PERCENTAGE = "foiling_percentage"
    TACK_COUNT = "tack_count"
    GYBE_COUNT = "gybe_count"
    FOILING_TACK_COUNT = "foiling_tack_count"
    FOILING_GYBE_COUNT = "foiling_gybe_count"
    FOILING_TACK_PERCENTAGE = "foiling_tack_percentage"
    FOILING_GYBE_PERCENTAGE = "foiling_gybe_percentage"
    MAX_BOAT_SPEED = "max_boat_speed"
    SESSION_DISTANCE = "session_distance_nm"
    SESSION_DURATION = "session_duration_min"
    AVG_WIND_GUST = "avg_wind_gust_kn"
    AVG_WIND_SPEED = "avg_wind_speed_kn"
    AVG_WIND_DIRECTION = "avg_wind_dir"
