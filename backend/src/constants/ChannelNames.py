from enum import Enum


class ChannelNames(Enum):
    LATITUDE = "lat"
    LONGITUDE = "lon"
    HEART_RATE = "heart_rate"
    SOG = "sog"
    HEADING = "hdt"
    COG = "cog"
    TURN_RATE = "turn_rate"
    TWA = "twa"
    TWD = "twd"
    HEEL = "heel"
    PITCH = "pitch"
    VMG = "vmg"
    TIME_TO_GUN = "ttg"
    FOILING = "foiling"
    TWG_EXTERNAL = "twg_external"
    TWD_EXTERNAL = "twd_external"
    TWS_EXTERNAL = "tws_external"
    GPS_ACCURACY = "gps_acc"
    GPS_SATELLITES = "gps_satellites"
