import numpy as np
import pytest

from src.analyzer.foilingAnalyzer import FoilingAnalyzer
from src.constants.ChannelNames import ChannelNames
from src.constants.MetricNames import MetricNames
from src.models.canonicalSession import (CanonicalSession, Channel,
                                         SessionMetadata)


@pytest.fixture
def session() -> CanonicalSession:
    return CanonicalSession(
        metadata=SessionMetadata(session_id="session-foiling"),
        channels={
            ChannelNames.LATITUDE.value: Channel(
                name=ChannelNames.LATITUDE.value,
                timestamps=np.array([0.0, 60.0, 120.0, 180.0]),
                values=np.array([57.0, 57.0, 57.0, 57.0]),
                unit="deg",
                source="gps",
            ),
            ChannelNames.LONGITUDE.value: Channel(
                name=ChannelNames.LONGITUDE.value,
                timestamps=np.array([0.0, 60.0, 120.0, 180.0]),
                values=np.array([11.0, 11.0, 11.0, 11.0]),
                unit="deg",
                source="gps",
            ),
            ChannelNames.SOG.value: Channel(
                name=ChannelNames.SOG.value,
                timestamps=np.array([0.0, 60.0, 120.0, 180.0]),
                values=np.array([10.0, 12.0, 13.5, 11.0]),
                unit="kn",
                source="gps",
            ),
        },
    )


def test_init_rejects_non_positive_threshold() -> None:
    with pytest.raises(
        ValueError, match="foiling_speed_knots must be greater than 0"
    ):
        FoilingAnalyzer(0.0)


def test_analyze_adds_foiling_channel_and_provenance(
    session: CanonicalSession,
) -> None:
    analyzer = FoilingAnalyzer(12.0)

    result = analyzer.analyze(session)

    assert result is session
    assert result.has_channel(ChannelNames.FOILING.value)

    foiling_channel = result.get_channel(ChannelNames.FOILING.value)
    assert foiling_channel.unit is None
    assert foiling_channel.source == "FoilingAnalyzer"
    assert foiling_channel.is_derived is True
    assert foiling_channel.metadata == {
        "channel": ChannelNames.SOG.value,
        "threshold_kn": 12.0,
        "comparison": "greater_than_or_equal",
    }
    assert np.array_equal(
        foiling_channel.timestamps,
        result.get_channel(ChannelNames.SOG.value).timestamps,
    )
    assert np.array_equal(
        foiling_channel.values,
        np.array([False, True, True, False]),
    )

    foiling_time_metric = result.get_metric(MetricNames.FOILING_TIME.value)
    assert foiling_time_metric.value == pytest.approx(2.0)
    assert foiling_time_metric.unit == "min"
    assert foiling_time_metric.source == "FoilingAnalyzer"
    assert foiling_time_metric.metadata == {
        "channel": ChannelNames.SOG.value,
        "threshold_kn": 12.0,
        "comparison": "greater_than_or_equal",
    }

    foiling_percentage_metric = result.get_metric(
        MetricNames.FOILING_PERCENTAGE.value
    )
    assert foiling_percentage_metric.value == pytest.approx(66.6666666667)
    assert foiling_percentage_metric.unit == "percent"
    assert foiling_percentage_metric.source == "FoilingAnalyzer"
    assert foiling_percentage_metric.metadata == {
        "channel": ChannelNames.SOG.value,
        "threshold_kn": 12.0,
        "comparison": "greater_than_or_equal",
    }

    assert len(result.provenance) == 3
    records = {record.produced_name: record for record in result.provenance}

    foiling_record = records[ChannelNames.FOILING.value]
    assert foiling_record.producer == "FoilingAnalyzer"
    assert foiling_record.produced_type == "channel"
    assert foiling_record.inputs == [ChannelNames.SOG.value]
    assert foiling_record.config == {
        "channel": ChannelNames.SOG.value,
        "threshold_kn": 12.0,
        "comparison": "greater_than_or_equal",
    }
    assert foiling_record.changes == [
        {
            "field": "values",
            "operation": "threshold_classification",
            "description": "Classified foiling samples from boat speed threshold",
        }
    ]

    foiling_time_record = records[MetricNames.FOILING_TIME.value]
    assert foiling_time_record.producer == "FoilingAnalyzer"
    assert foiling_time_record.produced_type == "metric"
    assert foiling_time_record.inputs == [ChannelNames.SOG.value]
    assert foiling_time_record.config == {
        "channel": ChannelNames.SOG.value,
        "threshold_kn": 12.0,
        "comparison": "greater_than_or_equal",
        "unit": "min",
    }
    assert foiling_time_record.changes == [
        {
            "field": "value",
            "operation": "aggregate_duration",
            "description": "Computed total foiling time from boat speed threshold",
        }
    ]

    foiling_percentage_record = records[MetricNames.FOILING_PERCENTAGE.value]
    assert foiling_percentage_record.producer == "FoilingAnalyzer"
    assert foiling_percentage_record.produced_type == "metric"
    assert foiling_percentage_record.inputs == [ChannelNames.SOG.value]
    assert foiling_percentage_record.config == {
        "channel": ChannelNames.SOG.value,
        "threshold_kn": 12.0,
        "comparison": "greater_than_or_equal",
        "unit": "percent",
    }
    assert foiling_percentage_record.changes == [
        {
            "field": "value",
            "operation": "aggregate_percentage",
            "description": "Computed foiling percentage from boat speed threshold",
        }
    ]


def test_analyze_treats_nan_speeds_as_not_foiling() -> None:
    session = CanonicalSession(
        metadata=SessionMetadata(session_id="session-foiling-nan"),
        channels={
            ChannelNames.LATITUDE.value: Channel(
                name=ChannelNames.LATITUDE.value,
                timestamps=np.array([0.0, 60.0, 120.0]),
                values=np.array([57.0, 57.0, 57.0]),
                unit="deg",
                source="gps",
            ),
            ChannelNames.LONGITUDE.value: Channel(
                name=ChannelNames.LONGITUDE.value,
                timestamps=np.array([0.0, 60.0, 120.0]),
                values=np.array([11.0, 11.0, 11.0]),
                unit="deg",
                source="gps",
            ),
            ChannelNames.SOG.value: Channel(
                name=ChannelNames.SOG.value,
                timestamps=np.array([0.0, 60.0, 120.0]),
                values=np.array([12.0, np.nan, 13.0]),
                unit="kn",
                source="gps",
            ),
        },
    )

    result = FoilingAnalyzer(12.0).analyze(session)

    assert np.array_equal(
        result.get_channel(ChannelNames.FOILING.value).values,
        np.array([True, False, True]),
    )


def test_print_summary_outputs_fly_time_and_percentage(
    session: CanonicalSession, capsys: pytest.CaptureFixture[str]
) -> None:
    analyzer = FoilingAnalyzer(12.0)

    analyzer.analyze(session)
    analyzer.print_summary()

    assert (
        capsys.readouterr().out
        == "foiling: fly time 2.0 min (66.7% of session)\n"
    )
