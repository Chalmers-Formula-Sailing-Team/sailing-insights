from src.models.canonicalSession import Artifact


def test_artifact_valid_minimal():
    data = {"bins": [6, 8, 10], "vmg": [5.1, 5.8, 6.0]}

    artifact = Artifact(
        name="upwind_polar",
        data=data,
        artifact_type="polar_table",
    )

    assert artifact.name == "upwind_polar"
    assert artifact.data == data
    assert artifact.artifact_type == "polar_table"
    assert artifact.source is None
    assert artifact.metadata == {}


def test_artifact_valid_with_all_fields():
    data = {
        "rows": [
            {"segment_id": 1, "start": 10.0, "end": 25.0},
            {"segment_id": 2, "start": 40.0, "end": 55.0},
        ]
    }
    metadata = {"method": "v2", "validated": True}

    artifact = Artifact(
        name="detected_segments",
        data=data,
        artifact_type="segment_table",
        source="segment_detector",
        metadata=metadata,
    )

    assert artifact.name == "detected_segments"
    assert artifact.data == data
    assert artifact.artifact_type == "segment_table"
    assert artifact.source == "segment_detector"
    assert artifact.metadata == metadata


def test_artifact_accepts_dict_data():
    data = {"rmse": 0.14, "r2": 0.93}

    artifact = Artifact(
        name="fit_summary",
        data=data,
        artifact_type="model_fit",
    )

    assert artifact.data == {"rmse": 0.14, "r2": 0.93}


def test_artifact_accepts_list_data():
    data = [
        {"twa_bin": 40, "speed": 12.1},
        {"twa_bin": 45, "speed": 12.4},
    ]

    artifact = Artifact(
        name="polar_rows",
        data=data,
        artifact_type="table",
    )

    assert artifact.data == data


def test_artifact_accepts_string_data():
    artifact = Artifact(
        name="diagnostic_text",
        data="insufficient samples in downwind range",
        artifact_type="diagnostic",
    )

    assert artifact.data == "insufficient samples in downwind range"


def test_artifact_accepts_none_data():
    artifact = Artifact(
        name="empty_result",
        data=None,
        artifact_type="diagnostic",
    )

    assert artifact.data is None


def test_artifact_metadata_uses_independent_default_dict():
    artifact1 = Artifact(
        name="a1",
        data={"x": 1},
        artifact_type="summary_table",
    )
    artifact2 = Artifact(
        name="a2",
        data={"x": 2},
        artifact_type="summary_table",
    )

    artifact1.metadata["note"] = "generated from filtered set"

    assert artifact1.metadata == {"note": "generated from filtered set"}
    assert artifact2.metadata == {}
