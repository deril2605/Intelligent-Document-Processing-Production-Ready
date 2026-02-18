from __future__ import annotations

import logging

from opentelemetry import trace


class TraceContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        span = trace.get_current_span()
        ctx = span.get_span_context() if span is not None else None
        if ctx and ctx.is_valid:
            record.trace_id = format(ctx.trace_id, "032x")
            record.span_id = format(ctx.span_id, "016x")
        else:
            record.trace_id = "-"
            record.span_id = "-"
        return True


def configure_trace_logging() -> None:
    root = logging.getLogger()
    if not root.handlers:
        return

    for handler in root.handlers:
        has_filter = any(isinstance(f, TraceContextFilter) for f in handler.filters)
        if not has_filter:
            handler.addFilter(TraceContextFilter())

        formatter = handler.formatter
        if formatter is None:
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - "
                    "[trace_id=%(trace_id)s span_id=%(span_id)s] - %(message)s"
                )
            )
            continue

        fmt = getattr(formatter, "_fmt", "")
        if "trace_id=" in fmt and "span_id=" in fmt:
            continue

        handler.setFormatter(
            logging.Formatter(
                f"{fmt} [trace_id=%(trace_id)s span_id=%(span_id)s]",
                datefmt=getattr(formatter, "datefmt", None),
            )
        )

