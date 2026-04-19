from __future__ import annotations


def heartbeat_payload() -> dict:
    return {"event": "processor_heartbeat"}
