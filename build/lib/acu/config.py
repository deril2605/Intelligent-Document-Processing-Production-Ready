# src/acu/config.py
from __future__ import annotations

import os
from dataclasses import dataclass


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

    analyzer_id = os.getenv("ACU_ANALYZER_ID") or os.getenv("AZURE_AI_ANALYZER_ID")
    if not analyzer_id:
        raise RuntimeError("Missing env var: ACU_ANALYZER_ID (or AZURE_AI_ANALYZER_ID)")

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
