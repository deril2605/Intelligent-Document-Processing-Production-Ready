import os
from celery import Celery

celery_app = Celery(
    "credit_ocr_system",
    broker=os.environ["REDIS_URL"],
    backend=os.environ["REDIS_URL"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
)
