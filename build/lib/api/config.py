import os
from typing import Any, Dict


class ApiConfig:
    """Configuration for the FastAPI service."""

    def __init__(self) -> None:
        self.host: str = os.getenv("API_HOST", "127.0.0.1")
        self.port: int = int(os.getenv("API_PORT", "8000"))
        self.debug: bool = os.getenv("API_DEBUG", "false").lower() == "true"
        self.reload: bool = os.getenv("API_RELOAD", "false").lower() == "true"
        self.cors_origins: list[str] = self._parse_cors_origins()

    def _parse_cors_origins(self) -> list[str]:
        raw = os.getenv("CORS_ORIGINS", "*")
        if raw == "*":
            return ["*"]
        return [v.strip() for v in raw.split(",") if v.strip()]

    @property
    def is_production(self) -> bool:
        return os.getenv("ENVIRONMENT", "development").lower() == "production"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "debug": self.debug,
            "reload": self.reload,
            "cors_origins": self.cors_origins,
            "is_production": self.is_production,
        }
