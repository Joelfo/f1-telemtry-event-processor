from __future__ import annotations

from redis.asyncio import Redis


class RedisPublisher:
    def __init__(self, redis_client: Redis) -> None:
        self.redis_client = redis_client

    async def publish(self, channel: str, payload: bytes) -> None:
        if not channel:
            raise ValueError("channel is required")
        if not isinstance(payload, bytes):
            raise TypeError("payload must be bytes")
        await self.redis_client.publish(channel, payload)
