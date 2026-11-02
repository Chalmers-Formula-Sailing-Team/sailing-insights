from __future__ import annotations

from src.constants.ChannelNames import ChannelNames
from src.models.canonicalSession import CanonicalSession, ProvenanceRecord
from src.transformer.channelTransformer import ChannelTransformer
from src.utils.speed_conversion import mps_to_kn


class BoatSpeedTransformer(ChannelTransformer):
    CHANNELS_TO_TRANSFORM = (ChannelNames.SOG.value,)
    REQUIRED_CHANNELS = CHANNELS_TO_TRANSFORM

    def __init__(self) -> None:
        self._channel_conversion: dict[str, bool] = {}

    def _transform(self, session: CanonicalSession) -> CanonicalSession:
        self._channel_conversion = {}
        for channel_name in self.CHANNELS_TO_TRANSFORM:
            channel = session.get_channel(channel_name)

            if channel.unit == "m/s":
                channel.values = mps_to_kn(channel.values)
                channel.unit = "kn"
                self._channel_conversion[channel_name] = True
                continue

            if channel.unit == "kn":
                self._channel_conversion[channel_name] = False
                continue

            raise ValueError(
                "BoatSpeedTransformer only supports units 'm/s' or 'kn' for channel "
                f"'{channel_name}'; got '{channel.unit}'"
            )

        return session

    def build_provenance_records(
        self, session: CanonicalSession
    ) -> list[ProvenanceRecord]:
        records: list[ProvenanceRecord] = []

        for channel_name, was_converted in self._channel_conversion.items():
            operation = "unit_convert" if was_converted else "noop"
            description = (
                "Converted boat speed values from m/s to kn"
                if was_converted
                else "Boat speed already in knots; no conversion applied"
            )
            records.append(
                self.make_provenance_record(
                    channel_name,
                    inputs=[channel_name],
                    config={"target_unit": "kn"},
                    changes=[
                        {
                            "field": "unit",
                            "operation": operation,
                            "from": "m/s" if was_converted else "kn",
                            "to": "kn",
                            "description": description,
                        }
                    ],
                )
            )

        return records

    def print_summary(self) -> None:
        converted_channels = sorted(
            channel_name
            for channel_name, was_converted in self._channel_conversion.items()
            if was_converted
        )
        unchanged_channels = sorted(
            channel_name
            for channel_name, was_converted in self._channel_conversion.items()
            if not was_converted
        )

        print(
            "boat speed: "
            f"converted {len(converted_channels)} channel(s) to kn, "
            f"{len(unchanged_channels)} already in kn"
        )
