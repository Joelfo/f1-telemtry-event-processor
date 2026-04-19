from __future__ import annotations


class RedisPublisher:
    async def publish(self, channel: str, payload: bytes) -> None:
        _ = (channel, payload)
