from __future__ import annotations


def build_output_message(message_type: str, payload: dict) -> dict:
    return {"type": message_type, "payload": payload}
