from datetime import UTC, datetime

import numpy as np
from src.analyzer.videoAnalyzer import VideoAnalyzer


def test_prepare_overlay_channels_preserves_position() -> None:
    analyzer = VideoAnalyzer()

    prepared_channels = analyzer._prepare_overlay_channels(
        creation_time=datetime(2026, 6, 14, 10, 0, tzinfo=UTC),
        channels=[
            {
                "position": "top",
                "name": "sog",
                "unit": "kn",
                "data_type": "real",
                "samples": [
                    (datetime(2026, 6, 14, 10, 0, tzinfo=UTC), 12.3),
                ],
            },
            {
                "position": "left",
                "name": "time_utc",
                "unit": None,
                "data_type": "virtual_utc_time",
                "samples": [],
            },
        ],
    )

    assert [channel["position"] for channel in prepared_channels] == ["top", "left"]
    assert np.array_equal(prepared_channels[0]["sample_seconds"], np.array([0.0]))


def test_group_prepared_channels_by_position_keeps_side_assignments() -> None:
    analyzer = VideoAnalyzer()

    grouped_channels = analyzer._group_prepared_channels_by_position(
        [
            {"position": "top", "name": "sog"},
            {"position": "bottom", "name": "twa"},
            {"position": "top", "name": "utc_time"},
        ]
    )

    assert [channel["name"] for channel in grouped_channels["top"]] == [
        "sog",
        "utc_time",
    ]
    assert [channel["name"] for channel in grouped_channels["bottom"]] == ["twa"]
