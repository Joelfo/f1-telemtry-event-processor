from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence

from redis.asyncio import Redis


def _decode_channel_name(value: str | bytes) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


class RedisSubscriber:
    def __init__(self, redis_client: Redis, channels: Sequence[str]) -> None:
        self.redis_client = redis_client
        self.channels = list(channels)
        self._pubsub = None

    async def start(self) -> None:
        self._pubsub = self.redis_client.pubsub(ignore_subscribe_messages=True)
        await self._pubsub.subscribe(*self.channels)

    async def iter_messages(self) -> AsyncIterator[tuple[str, bytes]]:
        if self._pubsub is None:
            raise RuntimeError("RedisSubscriber.start() must be called before iter_messages()")

        while True:
            message = await self._pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=1.0,
            )
            if message is None:
                await asyncio.sleep(0)
                continue

            if message.get("type") != "message":
                continue

            channel = _decode_channel_name(message["channel"])
            data = message["data"]
            if not isinstance(data, bytes):
                continue
            yield channel, data

    async def close(self) -> None:
        if self._pubsub is not None:
            await self._pubsub.unsubscribe(*self.channels)
            await self._pubsub.close()
            self._pubsub = None
