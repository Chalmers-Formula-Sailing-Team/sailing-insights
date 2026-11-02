from __future__ import annotations

from src.models.canonicalSession import CanonicalSession, ProvenanceRecord
from src.transformer.channelTransformer import ChannelTransformer


class RideHeightOffsetTransformer(ChannelTransformer):
    HEIGHT_CHANNEL_NAME = "height_m"
    REQUIRED_CHANNELS = (HEIGHT_CHANNEL_NAME,)
    _CENTIMETERS_PER_METER = 100.0

    def __init__(self) -> None:
        self._applied_offset_cm: float | None = None
        self._applied_offset_m: float | None = None
        self._applied = False

    def _transform(self, session: CanonicalSession) -> CanonicalSession:
        channel = session.get_channel(self.HEIGHT_CHANNEL_NAME)
        offset_cm = session.metadata.extras.get("rideHeightOffsetCm")

        self._applied = False
        self._applied_offset_cm = None
        self._applied_offset_m = None

        if offset_cm is None:
            return session

        if channel.unit != "m":
            raise ValueError(
                "RideHeightOffsetTransformer only supports unit 'm' for channel "
                f"'{self.HEIGHT_CHANNEL_NAME}'; got '{channel.unit}'"
            )

        self._applied_offset_cm = float(offset_cm)
        self._applied_offset_m = self._applied_offset_cm / self._CENTIMETERS_PER_METER
        channel.values = channel.values + self._applied_offset_m
        self._applied = True
        return session

    def build_provenance_records(
        self, session: CanonicalSession
    ) -> list[ProvenanceRecord]:
        operation = "offset_apply" if self._applied else "noop"
        description = (
            f"Applied ride height offset of {self._applied_offset_cm:g} cm"
            if self._applied
            else "No ride height offset metadata provided; no offset applied"
        )

        return [
            self.make_provenance_record(
                self.HEIGHT_CHANNEL_NAME,
                inputs=[self.HEIGHT_CHANNEL_NAME],
                config={
                    "offset_cm": self._applied_offset_cm,
                    "offset_m": self._applied_offset_m,
                },
                changes=[
                    {
                        "field": "values",
                        "operation": operation,
                        "value_offset_cm": self._applied_offset_cm,
                        "value_offset_m": self._applied_offset_m,
                        "description": description,
                    }
                ],
            )
        ]

    def print_summary(self) -> None:
        if self._applied:
            print(
                "ride height: "
                f"applied offset {self._applied_offset_cm:g} cm "
                f"({self._applied_offset_m:g} m)"
            )
            return

        print("ride height: no offset applied")
