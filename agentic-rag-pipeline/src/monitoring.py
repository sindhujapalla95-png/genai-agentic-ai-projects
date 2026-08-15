"""
Lightweight structured monitoring + alerting.

Modeled on an Azure Monitor style workflow: every stage emits a structured
metric event; anything that breaches the configured SLA raises an alert
that a real deployment would forward to PagerDuty/Teams/Slack.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable

from src.config import settings

logger = logging.getLogger("agentic_rag.monitoring")
logging.basicConfig(level=logging.INFO)


@dataclass
class MetricEvent:
    name: str
    duration_ms: float
    success: bool
    metadata: dict = field(default_factory=dict)


class MetricsRegistry:
    """In-memory metrics store with an alert hook (swap for App Insights/Prometheus)."""

    def __init__(self, alert_sink: Callable[[str], None] | None = None) -> None:
        self._events: list[MetricEvent] = []
        self._counts: dict[str, int] = defaultdict(int)
        self._alert_sink = alert_sink or (lambda msg: logger.warning("ALERT: %s", msg))

    def record(self, event: MetricEvent) -> None:
        self._events.append(event)
        self._counts[event.name] += 1
        logger.info(
            "metric name=%s duration_ms=%.1f success=%s meta=%s",
            event.name,
            event.duration_ms,
            event.success,
            event.metadata,
        )
        if not event.success:
            self._alert_sink(f"{event.name} failed: {event.metadata}")
        elif event.duration_ms > settings.sla_latency_ms:
            self._alert_sink(
                f"{event.name} breached SLA "
                f"({event.duration_ms:.0f}ms > {settings.sla_latency_ms}ms)"
            )

    def error_rate(self, name: str) -> float:
        relevant = [e for e in self._events if e.name == name]
        if not relevant:
            return 0.0
        failures = sum(1 for e in relevant if not e.success)
        return failures / len(relevant)

    def mean_time_to_resolution_ms(self, name: str) -> float:
        """Average duration of failed events - a proxy MTTR signal."""
        failures = [e.duration_ms for e in self._events if e.name == name and not e.success]
        return sum(failures) / len(failures) if failures else 0.0

    def snapshot(self) -> dict:
        return {
            "total_events": len(self._events),
            "counts_by_name": dict(self._counts),
        }


metrics = MetricsRegistry()


@contextmanager
def timed(name: str, **metadata):
    """Context manager that times a block and records success/failure automatically."""
    start = time.perf_counter()
    success = True
    try:
        yield
    except Exception:
        success = False
        raise
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        metrics.record(MetricEvent(name=name, duration_ms=duration_ms, success=success, metadata=metadata))
