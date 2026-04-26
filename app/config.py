from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Settings:
    host: str
    port: int
    max_body_bytes: int
    session_ttl_seconds: int
    request_timeout_seconds: int
    log_level: str
    mws_fixture_dir: str

    def __init__(self) -> None:
        self.host = os.getenv("HOST", "0.0.0.0")
        self.port = int(os.getenv("PORT", "8000"))
        self.max_body_bytes = int(os.getenv("MAX_BODY_BYTES", str(1024 * 1024)))
        self.session_ttl_seconds = int(os.getenv("SESSION_TTL_SECONDS", "7200"))
        self.request_timeout_seconds = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "15"))
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        self.mws_fixture_dir = os.getenv("MWS_FIXTURE_DIR", "").strip()

    @property
    def fixture_dir(self) -> Path | None:
        return Path(self.mws_fixture_dir) if self.mws_fixture_dir else None


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
