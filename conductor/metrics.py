"""
Prometheus metrics for Conductor Agent.
Implements ADR-5 from CND-ARCH: unified observability under conductor_* namespace.
"""

from typing import Optional
from prometheus_client import Counter, Histogram, start_http_server, REGISTRY

# Track whether server is already started
_metrics_server_started = False

# Metrics Definitions
conductor_runs_total = Counter(
    "conductor_runs_total",
    "Total Conductor pipeline execution runs by outcome status",
    ["status"],  # "completed", "failed", "aborted", "rejected"
)

conductor_node_duration_seconds = Histogram(
    "conductor_node_duration_seconds",
    "Duration of individual node executions in seconds",
    ["node"],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
)

conductor_node_errors_total = Counter(
    "conductor_node_errors_total",
    "Total errors encountered by node",
    ["node"],
)

conductor_token_cost_total = Counter(
    "conductor_token_cost_total",
    "Estimated token cost in USD by component",
    ["component"],
)

conductor_human_gate_actions_total = Counter(
    "conductor_human_gate_actions_total",
    "Total human-in-the-loop gate actions",
    ["action"],  # "approve", "edit", "reject", "abort"
)


def start_conductor_metrics_server(port: int = 8001) -> bool:
    """Start Prometheus HTTP metrics exporter server if not already running."""
    global _metrics_server_started
    if _metrics_server_started:
        return True
    try:
        start_http_server(port)
        _metrics_server_started = True
        print(f"[Metrics] Prometheus server running on port :{port} (/metrics)")
        return True
    except Exception as e:
        print(f"[Metrics WARNING] Failed to start Prometheus server on port {port}: {e}")
        return False
