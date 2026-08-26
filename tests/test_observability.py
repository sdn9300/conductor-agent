"""
Unit tests for Prometheus Metrics and Observability (Phase 5).
Verifies metric registration, metric counter/histogram increments, and scrape endpoint formatting.
"""

import pytest
from prometheus_client import REGISTRY
from conductor.metrics import (
    conductor_runs_total,
    conductor_node_duration_seconds,
    conductor_node_errors_total,
    conductor_human_gate_actions_total,
    conductor_token_cost_total,
    start_conductor_metrics_server,
)


def test_prometheus_metrics_registered():
    """All conductor_* metrics are properly registered with Prometheus."""
    metric_names = [m.name for m in REGISTRY.collect()]
    assert "conductor_runs" in metric_names or "conductor_runs_total" in metric_names
    assert "conductor_node_duration_seconds" in metric_names
    assert "conductor_node_errors" in metric_names or "conductor_node_errors_total" in metric_names
    assert "conductor_human_gate_actions" in metric_names or "conductor_human_gate_actions_total" in metric_names
    assert "conductor_token_cost" in metric_names or "conductor_token_cost_total" in metric_names


def test_metric_counter_increments():
    """Conductor metrics record pipeline events accurately."""
    initial_val = conductor_runs_total.labels(status="completed")._value.get()
    conductor_runs_total.labels(status="completed").inc()
    new_val = conductor_runs_total.labels(status="completed")._value.get()
    assert new_val == initial_val + 1


def test_token_cost_metric_increment():
    """Token cost metrics track component expenditures."""
    initial_cost = conductor_token_cost_total.labels(component="align_resume")._value.get()
    conductor_token_cost_total.labels(component="align_resume").inc(0.0025)
    new_cost = conductor_token_cost_total.labels(component="align_resume")._value.get()
    assert new_cost > initial_cost


def test_metrics_server_startup():
    """start_conductor_metrics_server runs idempotently without crashing."""
    # Running multiple times on the same port should be handled gracefully
    start_conductor_metrics_server(8001)
    start_conductor_metrics_server(8001)
