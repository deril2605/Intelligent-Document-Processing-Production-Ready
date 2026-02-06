from credit_ocr_system.celery_app import celery_app

@celery_app.task
def ping():
    return "pong"
