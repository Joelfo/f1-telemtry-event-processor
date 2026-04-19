import logging

import pytest

from ep.bus.codec_msgpack import (
    MessageDecodeError,
    decode_message,
    decode_message_or_none,
    encode_message,
)


def test_encode_decode_round_trip() -> None:
    message = {"v": 1, "payload": {"speed_kph": 300}}
    encoded = encode_message(message)
    decoded = decode_message(encoded)
    assert decoded == message


def test_decode_message_raises_for_invalid_payload() -> None:
    with pytest.raises(MessageDecodeError):
        decode_message(b"\xff\xff\xff")


def test_decode_message_or_none_logs_and_drops_corrupt_payload(caplog) -> None:
    logger = logging.getLogger("test.codec")
    with caplog.at_level(logging.WARNING):
        decoded = decode_message_or_none(b"\xff\xff\xff", logger, channel="lap_data")
    assert decoded is None
    assert "dropped_invalid_msgpack" in caplog.text
