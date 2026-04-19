from __future__ import annotations

from copy import deepcopy
from typing import Any


def build_default_snapshot(*, session_uid: int | None, player_car_index: int | None) -> dict:
    return {
        "v": 1,
        "session_uid": session_uid,
        "player_car_index": player_car_index,
        "updated_at_ns": 0,
        "player": {
            "car": {
                "speed_kph": 0,
                "throttle_pct": 0,
                "brake_pct": 0,
                "steer_pct": 0,
                "gear": 0,
                "engine_rpm": 0,
                "drs_enabled": False,
                "ers_store_energy_j": 0,
            },
            "lap": {
                "lap_number": 0,
                "current_lap_time_ms": 0,
                "last_lap_time_ms": None,
                "best_lap_time_ms": None,
                "delta_to_best_ms": None,
                "delta_to_last_ms": None,
                "sector": 1,
            },
            "tyres": {
                "surface_temp_c": {"rl": 0, "rr": 0, "fl": 0, "fr": 0},
                "inner_temp_c": {"rl": 0, "rr": 0, "fl": 0, "fr": 0},
                "wear_pct": {"rl": 0, "rr": 0, "fl": 0, "fr": 0},
                "avg_surface_temp_c": 0,
                "avg_wear_pct": 0,
                "wear_rate_pct_per_min": None,
            },
        },
    }


class SnapshotStore:
    def __init__(self) -> None:
        self._snapshot = build_default_snapshot(session_uid=None, player_car_index=None)

    def get_snapshot(self) -> dict:
        return deepcopy(self._snapshot)

    def reset(self, *, session_uid: int, player_car_index: int, updated_at_ns: int = 0) -> dict:
        self._snapshot = build_default_snapshot(
            session_uid=session_uid,
            player_car_index=player_car_index,
        )
        self._snapshot["updated_at_ns"] = updated_at_ns
        return self.get_snapshot()

    def apply_patch(
        self,
        *,
        path: str,
        value: Any,
        source_type: str,
        updated_at_ns: int | None = None,
    ) -> dict:
        if not path or path.startswith(".") or path.endswith("."):
            raise ValueError("Invalid patch path")
        if not source_type:
            raise ValueError("source_type is required")

        keys = path.split(".")
        cursor = self._snapshot
        for key in keys[:-1]:
            next_value = cursor.get(key)
            if next_value is None:
                next_value = {}
                cursor[key] = next_value
            if not isinstance(next_value, dict):
                raise ValueError(f"Patch path segment '{key}' is not a mapping")
            cursor = next_value

        cursor[keys[-1]] = value

        if updated_at_ns is not None:
            self._snapshot["updated_at_ns"] = updated_at_ns

        return {
            "path": path,
            "value": value,
            "source_type": source_type,
        }
