from __future__ import annotations

import asyncio

import pytest

from ep.bus.codec_msgpack import decode_message, encode_message
from ep.pipeline.orchestrator import Orchestrator
from ep.pipeline.router import DERIVED_CAR_CHANNEL, META_CHANNEL, Router
from ep.state.session_guard import SessionGuard
from ep.state.snapshot_store import SnapshotStore


class FakePublisher:
    def __init__(self) -> None:
        self.published: list[tuple[str, bytes]] = []

    async def publish(self, channel: str, payload: bytes) -> None:
        self.published.append((channel, payload))


class FakeSubscriber:
    def __init__(self, messages: list[tuple[str, bytes]], *, fail_on_start: bool = False) -> None:
        self.messages = messages
        self.fail_on_start = fail_on_start
        self.closed = False

    async def start(self) -> None:
        if self.fail_on_start:
            raise RuntimeError("simulated start failure")

    async def iter_messages(self):
        for topic, payload in self.messages:
            yield topic, payload

    async def close(self) -> None:
        self.closed = True


def _event(*, frame: int) -> dict:
    return {
        "v": 1,
        "packet_type": 6,
        "session_uid": 123,
        "session_time": 1.0,
        "frame_identifier": frame,
        "overall_frame_identifier": frame,
        "player_car_index": 0,
        "car_idx": None,
        "ingested_at": 10.5,
        "payload": {
            "speed_kph": 301,
            "throttle": 0.7,
            "brake": 0.1,
            "steer": 0.0,
            "gear": 7,
            "engine_rpm": 12000,
            "drs": False,
            "tyres_surface_temp": [80, 81, 82, 83],
            "tyres_inner_temp": [90, 91, 92, 93],
        },
    }


@pytest.mark.asyncio
async def test_orchestrator_processes_message_and_updates_snapshot() -> None:
    publisher = FakePublisher()
    snapshot_store = SnapshotStore()
    orchestrator = Orchestrator(
        subscriber_factory=lambda: FakeSubscriber([]),
        publisher=publisher,
        router=Router(),
        session_guard=SessionGuard(),
        snapshot_store=snapshot_store,
        heartbeat_seconds=60,
    )

    processed = await orchestrator._process_raw_message("car_telemetry", encode_message(_event(frame=1)))

    assert processed is True
    channels = [channel for channel, _ in publisher.published]
    assert META_CHANNEL in channels
    assert DERIVED_CAR_CHANNEL in channels
    assert snapshot_store.get_snapshot()["player"]["car"]["speed_kph"] == 301


@pytest.mark.asyncio
async def test_orchestrator_reconnects_after_subscriber_failure() -> None:
    publisher = FakePublisher()
    messages = [("car_telemetry", encode_message(_event(frame=2)))]

    failing_subscriber = FakeSubscriber([], fail_on_start=True)
    working_subscriber = FakeSubscriber(messages)
    subscribers = [failing_subscriber, working_subscriber]

    def subscriber_factory() -> FakeSubscriber:
        return subscribers.pop(0)

    orchestrator = Orchestrator(
        subscriber_factory=subscriber_factory,
        publisher=publisher,
        router=Router(),
        session_guard=SessionGuard(),
        snapshot_store=SnapshotStore(),
        heartbeat_seconds=60,
        reconnect_delay_seconds=0.0,
    )

    await orchestrator.run(max_messages=1)

    channels = [channel for channel, _ in publisher.published]
    assert DERIVED_CAR_CHANNEL in channels
    assert working_subscriber.closed is True


@pytest.mark.asyncio
async def test_orchestrator_drops_out_of_order_event() -> None:
    publisher = FakePublisher()
    orchestrator = Orchestrator(
        subscriber_factory=lambda: FakeSubscriber([]),
        publisher=publisher,
        router=Router(),
        session_guard=SessionGuard(),
        snapshot_store=SnapshotStore(),
        heartbeat_seconds=60,
    )

    await orchestrator._process_raw_message("car_telemetry", encode_message(_event(frame=10)))
    first_count = len(publisher.published)

    processed = await orchestrator._process_raw_message("car_telemetry", encode_message(_event(frame=9)))

    assert processed is False
    assert len(publisher.published) == first_count

    decoded_messages = [decode_message(payload) for _, payload in publisher.published]
    assert any(message["type"] == "car_metrics" for message in decoded_messages)
