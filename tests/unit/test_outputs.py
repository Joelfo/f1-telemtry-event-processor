import pytest

from ep.contracts.outputs import OutputEnvelopeError, build_output_message


def test_build_output_message_includes_required_fields() -> None:
    message = build_output_message(
        message_type="car_metrics",
        payload={"speed_kph": 300},
        session_uid=123,
        overall_frame_identifier=1500,
        player_car_index=0,
        ts_monotonic_ns=10,
    )
    assert message == {
        "v": 1,
        "type": "car_metrics",
        "session_uid": 123,
        "overall_frame_identifier": 1500,
        "ts_monotonic_ns": 10,
        "player_car_index": 0,
        "payload": {"speed_kph": 300},
    }


def test_build_output_message_rejects_invalid_player_index() -> None:
    with pytest.raises(OutputEnvelopeError):
        build_output_message(
            message_type="car_metrics",
            payload={},
            session_uid=123,
            overall_frame_identifier=1,
            player_car_index=99,
            ts_monotonic_ns=10,
        )
