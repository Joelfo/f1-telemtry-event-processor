from __future__ import annotations

from typing import Any


WHEEL_KEYS = ("rl", "rr", "fl", "fr")


class TyreMetricsProcessor:
    def process(self, event: dict) -> dict | None:
        if event.get("packet_type") != 6:
            return None

        payload = event.get("payload")
        if not isinstance(payload, dict):
            return None

        surface_values = payload.get("tyres_surface_temp")
        inner_values = payload.get("tyres_inner_temp")
        if not self._is_valid_wheel_array(surface_values) or not self._is_valid_wheel_array(inner_values):
            return None

        surface_temp_c = {key: int(surface_values[idx]) for idx, key in enumerate(WHEEL_KEYS)}
        inner_temp_c = {key: int(inner_values[idx]) for idx, key in enumerate(WHEEL_KEYS)}

        avg_surface_temp_c = sum(surface_temp_c.values()) / 4.0
        wear_pct = {key: 0 for key in WHEEL_KEYS}

        return {
            "surface_temp_c": surface_temp_c,
            "inner_temp_c": inner_temp_c,
            "wear_pct": wear_pct,
            "avg_surface_temp_c": avg_surface_temp_c,
            "avg_wear_pct": 0.0,
            "wear_rate_pct_per_min": None,
        }

    @staticmethod
    def _is_valid_wheel_array(value: Any) -> bool:
        if not isinstance(value, list) or len(value) != 4:
            return False
        return all(isinstance(item, int) and not isinstance(item, bool) for item in value)
