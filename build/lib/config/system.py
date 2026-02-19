# src/config/system.py

import os
from dataclasses import dataclass
from urllib.parse import urlparse


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


# -------------------------
# AZURE STORAGE
# -------------------------
@dataclass
class AzureStorageConfig:
    account_name: str
    account_key: str
    container_name: str = "documents"

    @property
    def connection_string(self) -> str:
        return (
            f"DefaultEndpointsProtocol=https;"
            f"AccountName={self.account_name};"
            f"AccountKey={self.account_key};"
            f"EndpointSuffix=core.windows.net"
        )


# -------------------------
# POSTGRES DATABASE
# -------------------------
@dataclass
class DatabaseConfig:
    host: str
    port: int
    name: str
    user: str
    password: str

    @property
    def psycopg2_dsn(self) -> dict:
        return dict(
            host=self.host,
            port=self.port,
            database=self.name,
            user=self.user,
            password=self.password,
        )


# -------------------------
# REDIS / CELERY
# -------------------------
@dataclass
class RedisConfig:
    host: str
    port: int

    task_serializer: str = "json"
    result_serializer: str = "json"
    accept_content: list = ("json",)
    timezone: str = "UTC"
    enable_utc: bool = True

    @property
    def broker_url(self) -> str:
        return f"redis://{self.host}:{self.port}/0"

    @property
    def result_backend(self) -> str:
        return f"redis://{self.host}:{self.port}/0"


# -------------------------
# OPTIONAL: AZURE CONTENT UNDERSTANDING (ACU)
# -------------------------
@dataclass
class AcuConfig:
    endpoint: str
    api_key: str
    analyzer_id: str


# -------------------------
# API SERVICE
# -------------------------
@dataclass
class ApiConfig:
    host: str
    port: int


# -------------------------
# MAIN APP CONFIG
# -------------------------
class AppConfig:
    """
    Central configuration object for the entire system.
    """

    def __init__(self):
        # 🔵 Azure Blob (Cloud)
        self.azure = type("Azure", (), {})()
        self.azure.storage = AzureStorageConfig(
            account_name="YOUR_STORAGE_ACCOUNT_NAME",
            account_key="YOUR_STORAGE_ACCOUNT_KEY",
            container_name=os.getenv("AZURE_BLOB_CONTAINER", "documents"),
        )

        # 🟢 PostgreSQL
        self.database = DatabaseConfig(
            host=_required_env("PGHOST"),
            port=int(_required_env("PGPORT")),
            name=_required_env("PGDATABASE"),
            user=_required_env("PGUSER"),
            password=_required_env("PGPASSWORD"),
        )

        # 🟡 Redis (for Celery)
        redis_url = _required_env("REDIS_URL")
        redis_host = _required_env("REDIS_HOST") if os.getenv("REDIS_HOST") else ""
        redis_port = int(_required_env("REDIS_PORT")) if os.getenv("REDIS_PORT") else 0
        if redis_url:
            parsed = urlparse(redis_url)
            if parsed.hostname:
                redis_host = parsed.hostname
            if parsed.port:
                redis_port = parsed.port
        if not redis_host or not redis_port:
            raise RuntimeError("REDIS_URL must include host and port")
        self.redis = RedisConfig(host=redis_host, port=redis_port)

        # 🔴 ACU (Azure Content Understanding)
        self.acu = AcuConfig(
            endpoint=os.getenv("AZURE_AI_ENDPOINT", "https://YOUR-ACU-RESOURCE.cognitiveservices.azure.com/"),
            api_key=os.getenv("AZURE_AI_API_KEY", "YOUR_ACU_KEY"),
            analyzer_id=os.getenv("ACU_ANALYZER_ID", os.getenv("AZURE_AI_ANALYZER_ID", "your-analyzer-id")),
        )

        # API service
        self.api = ApiConfig(
            host=os.getenv("API_HOST", "127.0.0.1"),
            port=int(os.getenv("API_PORT", "8000")),
        )
