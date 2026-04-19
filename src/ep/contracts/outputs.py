from __future__ import annotations

from collections.abc import Mapping
import time


class OutputEnvelopeError(Exception):
    pass


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def build_output_message(
    *,
    message_type: str,
    payload: Mapping[str, object],
    session_uid: int,
    overall_frame_identifier: int,
    player_car_index: int,
    ts_monotonic_ns: int | None = None,
    schema_version: int = 1,
) -> dict:
    if not message_type:
        raise OutputEnvelopeError("Field 'message_type' is required")

    if not _is_int(schema_version):
        raise OutputEnvelopeError("Field 'schema_version' must be int")
    if not _is_int(session_uid):
        raise OutputEnvelopeError("Field 'session_uid' must be int")
    if not _is_int(overall_frame_identifier):
        raise OutputEnvelopeError("Field 'overall_frame_identifier' must be int")
    if not _is_int(player_car_index):
        raise OutputEnvelopeError("Field 'player_car_index' must be int")
    if not 0 <= player_car_index <= 21:
        raise OutputEnvelopeError("Field 'player_car_index' out of range (expected 0..21)")
    if not isinstance(payload, Mapping):
        raise OutputEnvelopeError("Field 'payload' must be a mapping")

    emitted_ts = ts_monotonic_ns if ts_monotonic_ns is not None else time.monotonic_ns()
    if not _is_int(emitted_ts):
        raise OutputEnvelopeError("Field 'ts_monotonic_ns' must be int")

    return {
        "v": schema_version,
        "type": message_type,
        "session_uid": session_uid,
        "overall_frame_identifier": overall_frame_identifier,
        "ts_monotonic_ns": emitted_ts,
        "player_car_index": player_car_index,
        "payload": dict(payload),
    }
