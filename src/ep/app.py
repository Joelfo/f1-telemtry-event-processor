from __future__ import annotations

import argparse
import asyncio
import logging

from redis.asyncio import Redis

from ep.bus.redis_publisher import RedisPublisher
from ep.bus.redis_subscriber import RedisSubscriber
from ep.config import load_settings
from ep.logging import configure_logging
from ep.pipeline.orchestrator import INPUT_CHANNELS, Orchestrator
from ep.pipeline.router import Router
from ep.state.session_guard import SessionGuard
from ep.state.snapshot_store import SnapshotStore


logger = logging.getLogger("ep.app")


async def run_forever() -> None:
    settings = load_settings()
    redis_client = Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        password=settings.redis_password,
        decode_responses=False,
    )

    publisher = RedisPublisher(redis_client)

    def subscriber_factory() -> RedisSubscriber:
        return RedisSubscriber(redis_client, INPUT_CHANNELS)

    orchestrator = Orchestrator(
        subscriber_factory=subscriber_factory,
        publisher=publisher,
        router=Router(),
        session_guard=SessionGuard(),
        snapshot_store=SnapshotStore(),
        logger=logging.getLogger("ep.orchestrator"),
        heartbeat_seconds=settings.processor_heartbeat_seconds,
    )

    stop_event = asyncio.Event()
    try:
        await orchestrator.run(stop_event=stop_event)
    finally:
        await redis_client.aclose()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="F1 Event Processor")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run startup checks and exit immediately.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    settings = load_settings()
    configure_logging(settings.log_level)

    logger.info(
        "processor_started",
        extra={
            "redis_host": settings.redis_host,
            "redis_port": settings.redis_port,
            "redis_db": settings.redis_db,
            "heartbeat_seconds": settings.processor_heartbeat_seconds,
        },
    )

    if args.once:
        logger.info("startup_health_ok")
        return 0

    try:
        asyncio.run(run_forever())
    except KeyboardInterrupt:
        logger.info("processor_stopped")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
