import pytest
from src.models.canonicalSession import Metric


def test_metric_valid_minimal():
    metric = Metric(
        name="avg_upwind_speed", value=12.3, unit="kn", source="SpeedAnalyzer"
    )

    assert metric.name == "avg_upwind_speed"
    assert metric.value == 12.3
    assert metric.unit == "kn"
    assert metric.source == "SpeedAnalyzer"
    assert metric.metadata == {}


def test_metric_valid_with_all_fields():
    metadata = {"window": "leg_1", "method": "mean"}

    metric = Metric(
        name="best_vmg",
        value=9.87,
        unit="kn",
        source="analysis_pipeline",
        metadata=metadata,
    )

    assert metric.name == "best_vmg"
    assert metric.value == 9.87
    assert metric.unit == "kn"
    assert metric.source == "analysis_pipeline"
    assert metric.metadata == metadata


def test_metric_raises_no_source_provided():
    with pytest.raises(
        ValueError,
        match=r"Metric 'avg_upwind_speed' must have a source",
    ):
        Metric(name="avg_upwind_speed", value=12.3, unit="kn", source=None)


def test_metric_raises_no_unit_provided():
    with pytest.raises(
        ValueError,
        match=r"Metric 'avg_upwind_speed' must have a unit",
    ):
        Metric(name="avg_upwind_speed", value=12.3, source="knotMaster", unit=None)


def test_metric_accepts_non_numeric_value():
    metric = Metric(name="race_status", value="finished", unit="status", source="Racer")

    assert metric.name == "race_status"
    assert metric.value == "finished"


def test_metric_accepts_complex_value_types():
    metric = Metric(
        name="summary",
        value={"tacks": 4, "gybes": 2},
        unit="maneuver_dict",
        source="badManeuvers",
    )

    assert metric.value == {"tacks": 4, "gybes": 2}


def test_metric_metadata_uses_independent_default_dict():
    metric1 = Metric(name="max_heel", value=22.5, unit="degrees", source="highHeels")
    metric2 = Metric(name="number_of_tacks", value=6, unit="amt", source="Tacos")

    metric1.metadata["note"] = "computed from filtered data"

    assert metric1.metadata == {"note": "computed from filtered data"}
    assert metric2.metadata == {}


def test_metric_supports_none_value_if_needed():
    metric = Metric(
        name="optional_result", value=None, unit="optional", source="youChoose"
    )

    assert metric.name == "optional_result"
    assert metric.value is None
