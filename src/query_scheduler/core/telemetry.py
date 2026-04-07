"""OpenTelemetry bootstrap — import before FastAPI to auto-instrument."""

import os


def setup_telemetry() -> None:
    """Initialize OpenTelemetry SDK if OTEL_ENABLED=true.

    Reads from os.environ directly (not via settings) to avoid
    import-order coupling with pydantic-settings. Must be called
    before FastAPI app creation.
    """
    if os.getenv("OTEL_ENABLED", "false").lower() not in ("true", "1", "yes"):
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as e:
        import logging

        logging.getLogger(__name__).warning(
            "OTEL_ENABLED=true but opentelemetry packages not installed. "
            "Run: uv sync --extra otel. Error: %s",
            e,
        )
        return

    service_name = os.getenv("OTEL_SERVICE_NAME", "query_scheduler")
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    trace.set_tracer_provider(provider)


def shutdown_telemetry() -> None:
    """Flush and shut down the tracer provider."""
    try:
        from opentelemetry import trace

        provider = trace.get_tracer_provider()
        if hasattr(provider, "shutdown"):
            provider.shutdown()
    except ImportError:
        pass
