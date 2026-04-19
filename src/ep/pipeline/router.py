from __future__ import annotations


class Router:
    def route(self, topic: str, event: dict) -> None:
        _ = (topic, event)
