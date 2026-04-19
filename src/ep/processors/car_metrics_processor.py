from __future__ import annotations

from typing import Any


class CarMetricsProcessor:
    def __init__(self) -> None:
        self._latest_car_telemetry: dict[str, Any] | None = None
        self._latest_car_status: dict[str, Any] | None = None

    def process(self, event: dict) -> dict | None:
        packet_type = event.get("packet_type")
        payload = event.get("payload")

        if packet_type not in (6, 7) or not isinstance(payload, dict):
            return None

        if packet_type == 6:
            if not self._is_valid_car_telemetry_payload(payload):
                return None
            self._latest_car_telemetry = payload
        elif packet_type == 7:
            if not self._is_valid_car_status_payload(payload):
                return None
            self._latest_car_status = payload

        if self._latest_car_telemetry is None:
            return None

        telemetry = self._latest_car_telemetry
        status = self._latest_car_status or {}

        return {
            "speed_kph": int(telemetry["speed_kph"]),
            "throttle_pct": float(telemetry["throttle"]) * 100.0,
            "brake_pct": float(telemetry["brake"]) * 100.0,
            "steer_pct": float(telemetry["steer"]) * 100.0,
            "gear": int(telemetry["gear"]),
            "engine_rpm": int(telemetry["engine_rpm"]),
            "drs_enabled": bool(telemetry["drs"]),
            "ers_store_energy_j": float(status.get("ers_store_energy", 0.0)),
            "ers_deploy_mode": int(status.get("ers_deploy_mode", 0)),
            "ers_harvest_mguk_j": float(status.get("ers_harvested_this_lap_mguk", 0.0)),
            "ers_deployed_this_lap_j": float(status.get("ers_deployed_this_lap", 0.0)),
        }

    @staticmethod
    def _is_number(value: object) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    def _is_valid_car_telemetry_payload(self, payload: dict[str, Any]) -> bool:
        required_fields = (
            "speed_kph",
            "throttle",
            "brake",
            "steer",
            "gear",
            "engine_rpm",
            "drs",
        )
        if any(field not in payload for field in required_fields):
            return False

        if not isinstance(payload["drs"], bool):
            return False

        number_fields = ("speed_kph", "throttle", "brake", "steer", "gear", "engine_rpm")
        return all(self._is_number(payload[field]) for field in number_fields)

    def _is_valid_car_status_payload(self, payload: dict[str, Any]) -> bool:
        required_fields = (
            "ers_store_energy",
            "ers_deploy_mode",
            "ers_harvested_this_lap_mguk",
            "ers_deployed_this_lap",
        )
        if any(field not in payload for field in required_fields):
            return False
        return all(self._is_number(payload[field]) for field in required_fields)
