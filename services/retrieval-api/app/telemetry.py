"""OpenTelemetry setup.

Tracing is non-optional in this project: every operation that crosses a process
boundary emits a span (CLAUDE.md, "Guardrails"). This module owns the tracer
provider so the rest of the app just calls ``get_tracer()``.

Exporter behaviour:
  - If ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set, spans are batch-exported over OTLP
    to the collector.
  - If it is empty (local dev, CI), spans are still created and sampled so tests
    can assert on them, but nothing is shipped off-box.
"""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Tracer

from .config import Settings

_INITIALISED = False


def setup_telemetry(settings: Settings) -> None:
    """Install a global :class:`TracerProvider` for the process.

    Idempotent: calling it more than once (e.g. app reload, repeated tests) is a
    no-op after the first successful call.

    Args:
        settings: Resolved service settings; supplies the service name and the
            optional OTLP endpoint.
    """
    global _INITIALISED
    if _INITIALISED:
        return

    resource = Resource.create(
        {
            "service.name": settings.service_name,
            "service.version": "0.1.0",
            "deployment.environment": settings.environment,
        }
    )
    provider = TracerProvider(resource=resource)

    if settings.otel_endpoint:
        # Imported lazily so the OTLP/grpc dependency is only touched when used.
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )

        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_endpoint))
        )

    trace.set_tracer_provider(provider)
    _INITIALISED = True


def get_tracer() -> Tracer:
    """Return the tracer used throughout the service.

    Returns:
        The named :class:`~opentelemetry.trace.Tracer`. Safe to call before
        :func:`setup_telemetry`; it simply uses the default provider until then.
    """
    return trace.get_tracer("proofgate.retrieval-api")
