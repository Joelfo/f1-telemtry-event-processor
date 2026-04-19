from __future__ import annotations


class SnapshotStore:
    def __init__(self) -> None:
        self._snapshot: dict = {}

    def get_snapshot(self) -> dict:
        return dict(self._snapshot)
