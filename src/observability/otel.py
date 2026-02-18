from __future__ import annotations

import os
import threading

from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from .logging import configure_trace_logging

_init_lock = threading.Lock()
_initialized = False

def setup_observability(app=None) -> None:
    global _initialized
    connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if not connection_string:
        return

    with _init_lock:
        if not _initialized:
            resource = Resource.create(
                {
                    "service.name": os.getenv("OTEL_SERVICE_NAME", "intelligent-document-processing-api"),
                }
            )

            provider = TracerProvider(resource=resource)
            provider.add_span_processor(
                BatchSpanProcessor(
                    AzureMonitorTraceExporter(connection_string=connection_string)
                )
            )
            trace.set_tracer_provider(provider)

            RequestsInstrumentor().instrument()
            Psycopg2Instrumentor().instrument()
            RedisInstrumentor().instrument()
            configure_trace_logging()
            _initialized = True

    if app is not None and not getattr(app, "_otel_fastapi_instrumented", False):
        FastAPIInstrumentor.instrument_app(app)
        setattr(app, "_otel_fastapi_instrumented", True)
