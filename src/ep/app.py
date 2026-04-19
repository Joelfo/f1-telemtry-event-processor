from __future__ import annotations

import argparse
import asyncio
import logging

from ep.config import load_settings
from ep.logging import configure_logging


logger = logging.getLogger("ep.app")


async def run_forever() -> None:
    stop_event = asyncio.Event()
    await stop_event.wait()


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
