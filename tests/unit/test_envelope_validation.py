import pytest

from ep.contracts.envelope import EnvelopeValidationError, validate_input_envelope


def _valid_envelope() -> dict:
    return {
        "v": 1,
        "packet_type": 6,
        "session_uid": 123,
        "session_time": 1.5,
        "frame_identifier": 10,
        "overall_frame_identifier": 10,
        "player_car_index": 0,
        "car_idx": None,
        "ingested_at": 1550.1,
        "payload": {"speed_kph": 320},
    }


def test_validate_input_envelope_accepts_valid_event() -> None:
    event = _valid_envelope()
    validated = validate_input_envelope(event, topic="car_telemetry")
    assert validated == event


def test_validate_input_envelope_rejects_missing_field() -> None:
    event = _valid_envelope()
    event.pop("session_uid")
    with pytest.raises(EnvelopeValidationError):
        validate_input_envelope(event, topic="car_telemetry")


def test_validate_input_envelope_rejects_unsupported_version() -> None:
    event = _valid_envelope()
    event["v"] = 2
    with pytest.raises(EnvelopeValidationError):
        validate_input_envelope(event, topic="car_telemetry")


def test_validate_input_envelope_rejects_topic_packet_mismatch() -> None:
    event = _valid_envelope()
    event["packet_type"] = 2
    with pytest.raises(EnvelopeValidationError):
        validate_input_envelope(event, topic="car_telemetry")


def test_validate_input_envelope_rejects_non_null_car_idx_for_tier1() -> None:
    event = _valid_envelope()
    event["car_idx"] = 3
    with pytest.raises(EnvelopeValidationError):
        validate_input_envelope(event, topic="car_telemetry")
