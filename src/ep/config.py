from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None
    log_level: str = "INFO"
    processor_heartbeat_seconds: int = 5


def load_settings() -> Settings:
    redis_password = os.getenv("REDIS_PASSWORD", "")
    return Settings(
        redis_host=os.getenv("REDIS_HOST", "localhost"),
        redis_port=int(os.getenv("REDIS_PORT", "6379")),
        redis_db=int(os.getenv("REDIS_DB", "0")),
        redis_password=redis_password if redis_password else None,
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        processor_heartbeat_seconds=int(os.getenv("PROCESSOR_HEARTBEAT_SECONDS", "5")),
    )
