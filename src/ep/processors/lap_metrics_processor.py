from __future__ import annotations

from typing import Any


PIT_STATUS_MAP = {
    0: "none",
    1: "pitting",
    2: "in_pit_area",
}


class LapMetricsProcessor:
    def __init__(self) -> None:
        self._best_lap_time_ms: int | None = None

    def process(self, event: dict) -> dict | None:
        if event.get("packet_type") != 2:
            return None

        payload = event.get("payload")
        if not isinstance(payload, dict):
            return None
        if not self._is_valid_payload(payload):
            return None

        lap_number = int(payload["current_lap_num"])
        current_lap_time_ms = int(payload["current_lap_time_ms"])

        last_lap_raw = int(payload["last_lap_time_ms"])
        last_lap_time_ms = last_lap_raw if last_lap_raw > 0 else None

        if last_lap_time_ms is not None:
            if self._best_lap_time_ms is None or last_lap_time_ms < self._best_lap_time_ms:
                self._best_lap_time_ms = last_lap_time_ms

        best_lap_time_ms = self._best_lap_time_ms
        delta_to_best_ms = None if best_lap_time_ms is None else current_lap_time_ms - best_lap_time_ms
        delta_to_last_ms = None if last_lap_time_ms is None else current_lap_time_ms - last_lap_time_ms

        sector_raw = int(payload["sector"])
        sector = sector_raw + 1

        sector1_raw = int(payload["sector1_time_ms"])
        sector2_raw = int(payload["sector2_time_ms"])
        sector1_time_ms = sector1_raw if sector1_raw > 0 else None
        sector2_time_ms = sector2_raw if sector2_raw > 0 else None

        pit_status = PIT_STATUS_MAP[int(payload["pit_status"])]

        return {
            "lap_number": lap_number,
            "current_lap_time_ms": current_lap_time_ms,
            "last_lap_time_ms": last_lap_time_ms,
            "best_lap_time_ms": best_lap_time_ms,
            "delta_to_best_ms": delta_to_best_ms,
            "delta_to_last_ms": delta_to_last_ms,
            "sector": sector,
            "sector1_time_ms": sector1_time_ms,
            "sector2_time_ms": sector2_time_ms,
            "pit_status": pit_status,
        }

    @staticmethod
    def _is_number(value: object) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    def _is_valid_payload(self, payload: dict[str, Any]) -> bool:
        required_fields = (
            "current_lap_num",
            "current_lap_time_ms",
            "last_lap_time_ms",
            "sector",
            "sector1_time_ms",
            "sector2_time_ms",
            "pit_status",
        )
        if any(field not in payload for field in required_fields):
            return False
        if not all(self._is_number(payload[field]) for field in required_fields):
            return False

        sector_raw = int(payload["sector"])
        pit_status_raw = int(payload["pit_status"])
        if sector_raw not in (0, 1, 2):
            return False
        if pit_status_raw not in PIT_STATUS_MAP:
            return False
        return True
