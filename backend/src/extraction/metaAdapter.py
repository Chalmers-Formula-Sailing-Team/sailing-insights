import json

from src.models.raceModels import Race

from src.extraction.utils import parse_datetime, parse_float, parse_int


class MetaAdapter:
    def __init__(self, meta_file_path):
        with open(meta_file_path, "r", encoding="utf-8") as file:
            self.session_meta = json.load(file)

    def get_session_name(self):
        return self.session_meta.get("sessionName", "default session")

    def get_boat_name(self):
        return self.session_meta.get("boat")

    def get_location(self):
        return self.session_meta.get("location")

    def get_timezone(self):
        return self.session_meta.get("timezone")

    def get_start_ts(self):
        return parse_datetime(self.session_meta.get("start_ts"))

    def get_end_ts(self):
        return parse_datetime(self.session_meta.get("end_ts"))

    def get_manual_wind_amt(self):
        return parse_float(self.session_meta.get("windSpeed"))

    def get_manual_wind_gust(self):
        return parse_float(self.session_meta.get("windGust"))

    def get_manual_wind_dir(self):
        return parse_int(self.session_meta.get("windDirection"))

    def get_manual_wave_height(self):
        return parse_float(self.session_meta.get("waveHeightM"))

    def get_ride_height_offset_cm(self):
        return parse_float(
            self.session_meta.get(
                "rideHeightOffsetCm", self.session_meta.get("rideHightOffsetCm")
            )
        )

    def get_notes(self):
        notes = self.session_meta.get("notes")
        if notes is None:
            return None

        normalized_notes = str(notes).strip()
        return normalized_notes or None

    def get_exported_at(self):
        return self.session_meta.get("exportedAt")

    def get_races(self):
        return self._parse_races(self.session_meta.get("races", []))

    def _parse_races(self, races_payload: list[dict]) -> list[Race]:
        races: list[Race] = []

        for race_payload in races_payload:
            races.append(
                Race(
                    id=str(race_payload["id"]),
                    name=race_payload.get("name", ""),
                    start_at=parse_datetime(race_payload.get("startTime")),
                    finish_at=parse_datetime(race_payload.get("finish_ts")),
                )
            )

        return races
