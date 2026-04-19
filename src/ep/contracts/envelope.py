from __future__ import annotations

from collections.abc import Mapping


SUPPORTED_SCHEMA_VERSION = 1

TOPIC_PACKET_TYPE: dict[str, int] = {
    "lap_data": 2,
    "car_telemetry": 6,
    "car_status": 7,
    "motion_ex": 13,
}

TIER_1_TOPICS = frozenset(TOPIC_PACKET_TYPE.keys())

REQUIRED_FIELDS = (
    "v",
    "packet_type",
    "session_uid",
    "session_time",
    "frame_identifier",
    "overall_frame_identifier",
    "player_car_index",
    "car_idx",
    "ingested_at",
    "payload",
)


class EnvelopeValidationError(Exception):
    pass


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> bool:
    return (isinstance(value, (int, float))) and not isinstance(value, bool)


def validate_input_envelope(event: Mapping[str, object], *, topic: str) -> dict:
    missing_fields = [field for field in REQUIRED_FIELDS if field not in event]
    if missing_fields:
        raise EnvelopeValidationError(f"Missing envelope fields: {', '.join(missing_fields)}")

    envelope = dict(event)

    if not _is_int(envelope["v"]):
        raise EnvelopeValidationError("Field 'v' must be int")
    if envelope["v"] != SUPPORTED_SCHEMA_VERSION:
        raise EnvelopeValidationError(
            f"Unsupported schema version: {envelope['v']} (expected {SUPPORTED_SCHEMA_VERSION})"
        )

    if topic not in TOPIC_PACKET_TYPE:
        raise EnvelopeValidationError(f"Unsupported topic: {topic}")

    if not _is_int(envelope["packet_type"]):
        raise EnvelopeValidationError("Field 'packet_type' must be int")

    expected_packet_type = TOPIC_PACKET_TYPE[topic]
    if envelope["packet_type"] != expected_packet_type:
        raise EnvelopeValidationError(
            "packet_type/topic mismatch "
            f"(topic={topic}, packet_type={envelope['packet_type']}, expected={expected_packet_type})"
        )

    if not _is_int(envelope["session_uid"]):
        raise EnvelopeValidationError("Field 'session_uid' must be int")

    if not _is_number(envelope["session_time"]):
        raise EnvelopeValidationError("Field 'session_time' must be float|int")

    if not _is_int(envelope["frame_identifier"]):
        raise EnvelopeValidationError("Field 'frame_identifier' must be int")

    if not _is_int(envelope["overall_frame_identifier"]):
        raise EnvelopeValidationError("Field 'overall_frame_identifier' must be int")

    if not _is_int(envelope["player_car_index"]):
        raise EnvelopeValidationError("Field 'player_car_index' must be int")

    player_car_index = envelope["player_car_index"]
    if not 0 <= player_car_index <= 21:
        raise EnvelopeValidationError("Field 'player_car_index' out of range (expected 0..21)")

    if topic in TIER_1_TOPICS and envelope["car_idx"] is not None:
        raise EnvelopeValidationError("Field 'car_idx' must be null for Tier-1 topics")

    if not _is_number(envelope["ingested_at"]):
        raise EnvelopeValidationError("Field 'ingested_at' must be float|int")

    if not isinstance(envelope["payload"], dict):
        raise EnvelopeValidationError("Field 'payload' must be dict")

    return envelope
