# src/acu/config.py
from __future__ import annotations

import os
from dataclasses import dataclass

from src.config.system import HARDCODED_ACU_ANALYZERS


@dataclass(frozen=True)
class Settings:
    # ACU
    azure_ai_endpoint: str
    azure_ai_api_key: str | None
    acu_api_version: str
    acu_analyzer_id: str

    # Storage
    azure_storage_connection_string: str


def load_settings() -> Settings:
    endpoint = os.getenv("AZURE_AI_ENDPOINT")
    if not endpoint:
        raise RuntimeError("Missing env var: AZURE_AI_ENDPOINT")

    analyzer_id = HARDCODED_ACU_ANALYZERS.get("license-agreement")
    if not analyzer_id:
        raise RuntimeError("Missing hardcoded analyzer mapping for 'license-agreement'")

    storage_cs = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if not storage_cs:
        raise RuntimeError("Missing env var: AZURE_STORAGE_CONNECTION_STRING")

    return Settings(
        azure_ai_endpoint=endpoint,
        azure_ai_api_key=os.getenv("AZURE_AI_API_KEY"),
        acu_api_version=os.getenv("AZURE_AI_API_VERSION", "2025-11-01"),
        acu_analyzer_id=analyzer_id,
        azure_storage_connection_string=storage_cs,
    )
