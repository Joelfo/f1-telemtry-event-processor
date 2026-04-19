from __future__ import annotations

from collections.abc import Sequence


class RedisSubscriber:
    def __init__(self, channels: Sequence[str]) -> None:
        self.channels = list(channels)
