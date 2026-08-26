"""
Validation tests for Container & Infrastructure Manifests (Phase 5).
Verifies Dockerfile, Docker Compose, Prometheus alerts, Grafana dashboard, and Kubernetes manifests.
"""

import json
import os
from pathlib import Path
import pytest
import yaml

BASE_DIR = Path(__file__).resolve().parent.parent


def test_dockerfile_structure():
    """Dockerfile implements multi-stage build, non-root user, and healthcheck."""
    dockerfile_path = BASE_DIR / "Dockerfile"
    assert dockerfile_path.exists()
    content = dockerfile_path.read_text(encoding="utf-8")

    assert "AS builder" in content
    assert "AS runner" in content
    assert "useradd" in content or "conductor" in content
    assert "USER conductor" in content
    assert "HEALTHCHECK" in content
    assert "EXPOSE 8001" in content


def test_docker_compose_validity():
    """docker-compose.yml defines conductor, prometheus, and grafana services."""
    compose_path = BASE_DIR / "docker-compose.yml"
    assert compose_path.exists()
    data = yaml.safe_load(compose_path.read_text(encoding="utf-8"))

    assert "services" in data
    services = data["services"]
    assert "conductor" in services
    assert "prometheus" in services
    assert "grafana" in services
    assert "networks" in data
    assert "volumes" in data


def test_prometheus_and_alert_rules():
    """Prometheus scrape config and alerts parse as valid YAML with required rules."""
    prom_path = BASE_DIR / "deploy" / "prometheus" / "prometheus.yml"
    alerts_path = BASE_DIR / "deploy" / "prometheus" / "alerts.yml"
    assert prom_path.exists()
    assert alerts_path.exists()

    prom_data = yaml.safe_load(prom_path.read_text(encoding="utf-8"))
    assert "scrape_configs" in prom_data

    alerts_data = yaml.safe_load(alerts_path.read_text(encoding="utf-8"))
    assert "groups" in alerts_data
    rule_names = [r["alert"] for g in alerts_data["groups"] for r in g.get("rules", [])]
    assert "ConductorPipelineHighErrorRate" in rule_names
    assert "ConductorNodeLatencyHigh" in rule_names


def test_grafana_dashboard_json():
    """Grafana dashboard JSON parses and contains required panel visualizations."""
    dash_path = BASE_DIR / "deploy" / "grafana" / "dashboards" / "conductor_dashboard.json"
    assert dash_path.exists()

    data = json.loads(dash_path.read_text(encoding="utf-8"))
    assert data.get("title") == "Conductor Agent Orchestration Dashboard"
    assert "panels" in data
    assert len(data["panels"]) >= 4


def test_kubernetes_manifests():
    """Kubernetes manifests parse as valid YAML with required API objects."""
    k8s_dir = BASE_DIR / "deploy" / "k8s"
    assert k8s_dir.exists()

    manifest_files = [
        "conductor-pvc.yaml",
        "conductor-configmap.yaml",
        "conductor-deployment.yaml",
        "conductor-cronjob.yaml",
    ]

    for fname in manifest_files:
        path = k8s_dir / fname
        assert path.exists(), f"Missing K8s manifest: {fname}"
        docs = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
        assert len(docs) >= 1
        for doc in docs:
            assert "apiVersion" in doc
            assert "kind" in doc
            assert "metadata" in doc
