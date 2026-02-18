# src/celery_app.py

from celery import Celery
from src.config import AppConfig
from src.observability import setup_observability

# Load configuration from your AppConfig (same pattern as author)
app_config = AppConfig()
setup_observability()

# Create Celery instance
celery_app = Celery(
    "intelligent_doc_processing",
    broker=app_config.redis.broker_url,
    backend=app_config.redis.result_backend,
    include=["src.tasks.pipeline_tasks"],
)

# Apply configuration from AppConfig
celery_app.conf.update(
    # Serialization
    task_serializer=app_config.redis.task_serializer,
    accept_content=app_config.redis.accept_content,
    result_serializer=app_config.redis.result_serializer,

    # Timezone
    timezone=app_config.redis.timezone,
    enable_utc=app_config.redis.enable_utc,

    # Execution behavior
    task_track_started=True,
    task_time_limit=30 * 60,        # 30 min hard limit
    task_soft_time_limit=25 * 60,   # 25 min soft limit

    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_disable_rate_limits=False,
)

if __name__ == "__main__":
    celery_app.start()
