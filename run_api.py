#!/usr/bin/env python3
"""
Entry point for running the API service.
"""

from __future__ import annotations

import logging
import os

import uvicorn

from src.config import AppConfig


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _as_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def main() -> None:
    cfg = AppConfig()
    debug = _as_bool("API_DEBUG", default=False)
    reload_enabled = _as_bool("API_RELOAD", default=False)

    logger.info("Starting API service on %s:%s", cfg.api.host, cfg.api.port)

    uvicorn.run(
        "src.api.main:app",
        host=cfg.api.host,
        port=int(cfg.api.port),
        reload=reload_enabled,
        log_level="debug" if debug else "info",
        access_log=True,
    )


if __name__ == "__main__":
    main()

