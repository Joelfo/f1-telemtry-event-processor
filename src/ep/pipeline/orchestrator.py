from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable

from ep.bus.codec_msgpack import decode_message_or_none, encode_message
from ep.contracts.envelope import EnvelopeValidationError, validate_input_envelope
from ep.contracts.outputs import build_output_message
from ep.diagnostics.heartbeat import heartbeat_payload
from ep.pipeline.router import META_CHANNEL, STATE_PATCH_CHANNEL, Router
from ep.state.session_guard import SessionGuard
from ep.state.snapshot_store import SnapshotStore


INPUT_CHANNELS = ("car_telemetry", "lap_data", "car_status", "motion_ex")


class Orchestrator:
    def __init__(
        self,
        *,
        subscriber_factory: Callable[[], object],
        publisher: object,
        router: Router,
        session_guard: SessionGuard,
        snapshot_store: SnapshotStore,
        logger: logging.Logger | None = None,
        heartbeat_seconds: int = 5,
        reconnect_delay_seconds: float = 1.0,
    ) -> None:
        self.subscriber_factory = subscriber_factory
        self.publisher = publisher
        self.router = router
        self.session_guard = session_guard
        self.snapshot_store = snapshot_store
        self.logger = logger or logging.getLogger("ep.orchestrator")
        self.heartbeat_seconds = heartbeat_seconds
        self.reconnect_delay_seconds = reconnect_delay_seconds
        self._latest_session_uid = 0
        self._latest_player_car_index = 0
        self._latest_overall_frame_identifier = 0

    async def run(
        self,
        *,
        stop_event: asyncio.Event | None = None,
        max_messages: int | None = None,
    ) -> None:
        stop_event = stop_event or asyncio.Event()
        await self._publish_meta("processor_started", details={"channels": list(INPUT_CHANNELS)})

        processed = 0
        while not stop_event.is_set():
            subscriber = self.subscriber_factory()
            heartbeat_task: asyncio.Task | None = None
            try:
                await subscriber.start()
                heartbeat_task = asyncio.create_task(self._heartbeat_loop(stop_event))

                async for topic, raw_data in subscriber.iter_messages():
                    if stop_event.is_set():
                        break

                    processed_one = await self._process_raw_message(topic, raw_data)
                    if processed_one:
                        processed += 1
                        if max_messages is not None and processed >= max_messages:
                            stop_event.set()
                            break

            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger.exception("subscriber_loop_error")
                if not stop_event.is_set():
                    await asyncio.sleep(self.reconnect_delay_seconds)
            finally:
                if heartbeat_task is not None:
                    heartbeat_task.cancel()
                    try:
                        await heartbeat_task
                    except asyncio.CancelledError:
                        pass
                await subscriber.close()

    async def _process_raw_message(self, topic: str, raw_data: bytes) -> bool:
        event = decode_message_or_none(raw_data, self.logger, channel=topic)
        if event is None:
            return False

        try:
            envelope = validate_input_envelope(event, topic=topic)
        except EnvelopeValidationError:
            self.logger.warning("dropped_invalid_envelope", extra={"topic": topic})
            return False

        previous_session_uid = self.session_guard.session_uid
        try:
            decision = self.session_guard.evaluate(envelope)
        except ValueError:
            self.logger.warning("dropped_invalid_session_fields", extra={"topic": topic})
            return False

        self._latest_session_uid = int(envelope["session_uid"])
        self._latest_player_car_index = int(envelope["player_car_index"])
        self._latest_overall_frame_identifier = int(envelope["overall_frame_identifier"])

        if decision.session_changed:
            self.snapshot_store.reset(
                session_uid=self._latest_session_uid,
                player_car_index=self._latest_player_car_index,
                updated_at_ns=time.monotonic_ns(),
            )
            if previous_session_uid is None:
                await self._publish_meta("session_started", details={"session_uid": self._latest_session_uid})
            else:
                await self._publish_meta("session_reset", details={"session_uid": self._latest_session_uid})

        if not decision.should_process:
            return False

        routed_messages = self.router.route(topic, envelope)
        for message in routed_messages:
            wrapped = build_output_message(
                message_type=message.message_type,
                payload=message.payload,
                session_uid=self._latest_session_uid,
                overall_frame_identifier=self._latest_overall_frame_identifier,
                player_car_index=self._latest_player_car_index,
            )

            if message.channel == STATE_PATCH_CHANNEL:
                self.snapshot_store.apply_patch(
                    path=str(message.payload["path"]),
                    value=message.payload["value"],
                    source_type=str(message.payload["source_type"]),
                    updated_at_ns=wrapped["ts_monotonic_ns"],
                )

            await self.publisher.publish(message.channel, encode_message(wrapped))

        return True

    async def _heartbeat_loop(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            await asyncio.sleep(self.heartbeat_seconds)
            if stop_event.is_set():
                return
            await self._publish_meta("processor_heartbeat", details=heartbeat_payload())

    async def _publish_meta(self, event_name: str, *, details: dict) -> None:
        payload = {"event": event_name, "details": details}
        wrapped = build_output_message(
            message_type="meta",
            payload=payload,
            session_uid=self._latest_session_uid,
            overall_frame_identifier=self._latest_overall_frame_identifier,
            player_car_index=self._latest_player_car_index,
        )
        await self.publisher.publish(META_CHANNEL, encode_message(wrapped))
