from __future__ import annotations

from collections.abc import Mapping
import logging

import msgpack


class MessageCodecError(Exception):
    pass


class MessageDecodeError(MessageCodecError):
    pass


class MessageEncodeError(MessageCodecError):
    pass


def decode_message(data: bytes) -> dict:
    try:
        decoded = msgpack.unpackb(data, raw=False)
    except (msgpack.ExtraData, msgpack.FormatError, msgpack.StackError, ValueError, TypeError) as exc:
        raise MessageDecodeError("Failed to decode MessagePack payload") from exc

    if not isinstance(decoded, dict):
        raise MessageDecodeError("Decoded MessagePack payload must be a map")

    return decoded


def decode_message_or_none(data: bytes, logger: logging.Logger, *, channel: str | None = None) -> dict | None:
    try:
        return decode_message(data)
    except MessageDecodeError:
        logger.warning("dropped_invalid_msgpack", extra={"channel": channel})
        return None


def encode_message(message: Mapping[str, object]) -> bytes:
    try:
        return msgpack.packb(dict(message), use_bin_type=True)
    except (TypeError, ValueError) as exc:
        raise MessageEncodeError("Failed to encode message as MessagePack") from exc
