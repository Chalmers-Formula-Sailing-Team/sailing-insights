from src.models.canonicalSession import ProvenanceRecord


def test_provenance_record_valid_minimal():
    record = ProvenanceRecord(
        producer="vmg_analyzer",
        produced_type="metric",
        produced_name="best_vmg",
    )

    assert record.producer == "vmg_analyzer"
    assert record.produced_type == "metric"
    assert record.produced_name == "best_vmg"
    assert record.action == "created"
    assert record.inputs == []
    assert record.config == {}
    assert record.changes == []


def test_provenance_record_valid_with_all_fields():
    inputs = ["boat_speed", "twa", "sog"]
    config = {"window_s": 5, "min_samples": 20}
    changes = [
        {
            "field": "values",
            "operation": "remove_values",
            "indices": [4, 7, 8],
            "count": 3,
            "reason": "outlier cleanup",
            "description": "Removed invalid channel samples",
        }
    ]

    record = ProvenanceRecord(
        producer="channel_transformer",
        produced_type="channel",
        produced_name="boat_speed",
        action="modified",
        inputs=inputs,
        config=config,
        changes=changes,
    )

    assert record.producer == "channel_transformer"
    assert record.produced_type == "channel"
    assert record.produced_name == "boat_speed"
    assert record.action == "modified"
    assert record.inputs == inputs
    assert record.config == config
    assert record.changes == changes


def test_provenance_record_accepts_empty_strings():
    record = ProvenanceRecord(
        producer="",
        produced_type="",
        produced_name="",
        action="",
    )

    assert record.producer == ""
    assert record.produced_type == ""
    assert record.produced_name == ""
    assert record.action == ""


def test_provenance_record_accepts_empty_inputs_and_config():
    record = ProvenanceRecord(
        producer="segmenter",
        produced_type="event",
        produced_name="tack",
        inputs=[],
        config={},
        changes=[],
    )

    assert record.inputs == []
    assert record.config == {}
    assert record.changes == []


def test_provenance_record_inputs_uses_independent_default_list():
    record1 = ProvenanceRecord(
        producer="analyzer_a",
        produced_type="metric",
        produced_name="avg_speed",
    )
    record2 = ProvenanceRecord(
        producer="analyzer_b",
        produced_type="metric",
        produced_name="max_speed",
    )

    record1.inputs.append("sog")

    assert record1.inputs == ["sog"]
    assert record2.inputs == []


def test_provenance_record_config_uses_independent_default_dict():
    record1 = ProvenanceRecord(
        producer="analyzer_a",
        produced_type="channel",
        produced_name="filtered_speed",
    )
    record2 = ProvenanceRecord(
        producer="analyzer_b",
        produced_type="channel",
        produced_name="smoothed_speed",
    )

    record1.config["alpha"] = 0.2

    assert record1.config == {"alpha": 0.2}
    assert record2.config == {}


def test_provenance_record_changes_uses_independent_default_list():
    record1 = ProvenanceRecord(
        producer="transformer_a",
        produced_type="channel",
        produced_name="speed",
    )
    record2 = ProvenanceRecord(
        producer="transformer_b",
        produced_type="channel",
        produced_name="heel",
    )

    record1.changes.append({"field": "values", "operation": "clip", "max": 12.0})

    assert record1.changes == [{"field": "values", "operation": "clip", "max": 12.0}]
    assert record2.changes == []


def test_provenance_record_inputs_and_config_are_independent_on_same_instance():
    record = ProvenanceRecord(
        producer="event_detector",
        produced_type="event",
        produced_name="gybe",
    )

    record.inputs.append("awa")
    record.config["threshold"] = 35

    assert record.inputs == ["awa"]
    assert record.config == {"threshold": 35}


def test_provenance_record_can_describe_channel_value_removal():
    changes = [
        {
            "field": "values",
            "operation": "remove_values",
            "indices": [10, 11, 12],
            "count": 3,
            "reason": "sensor dropout",
            "description": "Removed samples from the channel",
        }
    ]

    record = ProvenanceRecord(
        producer="channel_transformer",
        produced_type="channel",
        produced_name="boat_speed",
        action="modified",
        inputs=["boat_speed"],
        config={"removal_strategy": "drop_invalid_samples"},
        changes=changes,
    )

    assert record.produced_type == "channel"
    assert record.action == "modified"
    assert record.changes == changes
