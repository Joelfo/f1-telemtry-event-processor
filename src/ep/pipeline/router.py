from __future__ import annotations

from dataclasses import dataclass

from ep.processors.car_metrics_processor import CarMetricsProcessor
from ep.processors.lap_metrics_processor import LapMetricsProcessor
from ep.processors.patch_emitter import PatchEmitter
from ep.processors.tyre_metrics_processor import TyreMetricsProcessor


DERIVED_CAR_CHANNEL = "ep.r1.player.derived.car_metrics"
DERIVED_LAP_CHANNEL = "ep.r1.player.derived.lap_metrics"
DERIVED_TYRE_CHANNEL = "ep.r1.player.derived.tyre_metrics"
STATE_PATCH_CHANNEL = "ep.r1.player.state.patch"
META_CHANNEL = "ep.r1.player.meta"


@dataclass(frozen=True)
class RoutedMessage:
    channel: str
    message_type: str
    payload: dict


class Router:
    def __init__(
        self,
        *,
        car_metrics_processor: CarMetricsProcessor | None = None,
        lap_metrics_processor: LapMetricsProcessor | None = None,
        tyre_metrics_processor: TyreMetricsProcessor | None = None,
        patch_emitter: PatchEmitter | None = None,
    ) -> None:
        self.car_metrics_processor = car_metrics_processor or CarMetricsProcessor()
        self.lap_metrics_processor = lap_metrics_processor or LapMetricsProcessor()
        self.tyre_metrics_processor = tyre_metrics_processor or TyreMetricsProcessor()
        self.patch_emitter = patch_emitter or PatchEmitter()

    def route(self, topic: str, event: dict) -> list[RoutedMessage]:
        messages: list[RoutedMessage] = []

        if topic in ("car_telemetry", "car_status"):
            car_payload = self.car_metrics_processor.process(event)
            if car_payload is not None:
                messages.append(
                    RoutedMessage(
                        channel=DERIVED_CAR_CHANNEL,
                        message_type="car_metrics",
                        payload=car_payload,
                    )
                )
                messages.extend(
                    self._build_state_patch_messages(
                        base_path="player.car",
                        payload=car_payload,
                        source_type="car_metrics",
                    )
                )

        if topic == "lap_data":
            lap_payload = self.lap_metrics_processor.process(event)
            if lap_payload is not None:
                messages.append(
                    RoutedMessage(
                        channel=DERIVED_LAP_CHANNEL,
                        message_type="lap_metrics",
                        payload=lap_payload,
                    )
                )
                messages.extend(
                    self._build_state_patch_messages(
                        base_path="player.lap",
                        payload=lap_payload,
                        source_type="lap_metrics",
                    )
                )

        if topic == "car_telemetry":
            tyre_payload = self.tyre_metrics_processor.process(event)
            if tyre_payload is not None:
                messages.append(
                    RoutedMessage(
                        channel=DERIVED_TYRE_CHANNEL,
                        message_type="tyre_metrics",
                        payload=tyre_payload,
                    )
                )
                messages.extend(
                    self._build_state_patch_messages(
                        base_path="player.tyres",
                        payload=tyre_payload,
                        source_type="tyre_metrics",
                    )
                )

        return messages

    def _build_state_patch_messages(
        self,
        *,
        base_path: str,
        payload: dict,
        source_type: str,
    ) -> list[RoutedMessage]:
        patches = self.patch_emitter.patches_from_payload(
            base_path=base_path,
            payload=payload,
            source_type=source_type,
        )
        return [
            RoutedMessage(
                channel=STATE_PATCH_CHANNEL,
                message_type="state_patch",
                payload=patch,
            )
            for patch in patches
        ]
