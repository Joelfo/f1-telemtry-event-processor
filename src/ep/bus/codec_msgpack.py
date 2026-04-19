from __future__ import annotations

import msgpack


def decode_message(data: bytes) -> dict:
    return msgpack.unpackb(data, raw=False)


def encode_message(message: dict) -> bytes:
    return msgpack.packb(message, use_bin_type=True)
