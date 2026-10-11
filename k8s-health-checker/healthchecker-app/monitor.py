"""
Health monitoring module — Sprint 2.

Polls the Kubernetes API for the GratitudeApp namespace and:
  - exposes Prometheus gauges for node readiness, pod restarts, pod phase,
    per-pod readiness (Ready condition), deployment replica availability,
    and a binary "all replicas available" gauge per deployment
  - provides plain-Python summaries used by the FastAPI routes
"""

import logging
import threading
import time

from prometheus_client import Gauge

from k8s_client import get_clients, list_deployments, list_nodes, list_pods

logger = logging.getLogger("monitor")

# GratitudeApp service deployment names
GRATITUDEAPP_SERVICES = [
    "client-deployment",
    "api-gateway-deployment",
    "entries-deployment",
    "moods-api-deployment",
    "moods-service-deployment",
    "stats-api-deployment",
    "stats-service-deployment",
    "files-service-deployment",
    "server-deployment",
    "postgres-deployment",
]

# ── Prometheus metrics ────────────────────────────────────────────────────────
NODE_READY = Gauge(
    "healthchecker_node_ready", "1 if node is Ready, 0 otherwise", ["node"]
)
POD_RESTARTS = Gauge(
    "healthchecker_pod_restarts_total",
    "Container restart count for a pod",
    ["namespace", "pod"],
)
POD_PHASE = Gauge(
    "healthchecker_pod_phase_running",
    "1 if pod phase is Running, 0 otherwise",
    ["namespace", "pod"],
)
POD_READY = Gauge(
    "healthchecker_pod_ready",
    "1 if pod Ready condition is True, 0 otherwise",
    ["namespace", "pod"],
)
DEPLOYMENT_AVAILABLE = Gauge(
    "healthchecker_deployment_available_replicas",
    "Available replicas for a deployment",
    ["namespace", "deployment"],
)
DEPLOYMENT_DESIRED = Gauge(
    "healthchecker_deployment_desired_replicas",
    "Desired replicas for a deployment",
    ["namespace", "deployment"],
)
DEPLOYMENT_ALL_AVAILABLE = Gauge(
    "healthchecker_deployment_all_replicas_available",
    "1 if available replicas == desired replicas, 0 otherwise",
    ["namespace", "deployment"],
)

DEFAULT_NAMESPACE = "default"
POLL_INTERVAL_SECONDS = 15


def collect_once(namespace: str = DEFAULT_NAMESPACE):
    """Fetch current cluster state, update Prometheus metrics, and
    return a JSON-friendly summary."""
    core, apps = get_clients()

    nodes = list_nodes(core)
    pods = list_pods(core, namespace)
    deployments = list_deployments(apps, namespace)

    # Clear previous gauge points so deleted pods/deployments don't linger
    NODE_READY.clear()
    POD_RESTARTS.clear()
    POD_PHASE.clear()
    POD_READY.clear()
    DEPLOYMENT_AVAILABLE.clear()
    DEPLOYMENT_DESIRED.clear()
    DEPLOYMENT_ALL_AVAILABLE.clear()

    # ── Nodes ─────────────────────────────────────────────────────────────────
    for node in nodes:
        NODE_READY.labels(node=node["name"]).set(
            1 if node["ready"] == "True" else 0
        )


    # ── Pods ──────────────────────────────────────────────────────────────────
    for pod in pods:
        POD_RESTARTS.labels(namespace=pod["namespace"], pod=pod["name"]).set(
            pod["restarts"]
        )
        POD_PHASE.labels(namespace=pod["namespace"], pod=pod["name"]).set(
            1 if pod["phase"] == "Running" else 0
        )
        POD_READY.labels(namespace=pod["namespace"], pod=pod["name"]).set(
            1 if pod.get("ready") else 0
        )

    # ── Deployments ───────────────────────────────────────────────────────────
    for dep in deployments:
        desired = dep["desired"] or 0
        available = dep["available"]
        DEPLOYMENT_AVAILABLE.labels(
            namespace=dep["namespace"], deployment=dep["name"]
        ).set(available)
        DEPLOYMENT_DESIRED.labels(
            namespace=dep["namespace"], deployment=dep["name"]
        ).set(desired)
        all_ok = 1 if (desired > 0 and available >= desired) else 0
        DEPLOYMENT_ALL_AVAILABLE.labels(
            namespace=dep["namespace"], deployment=dep["name"]
        ).set(all_ok)

    return {"nodes": nodes, "pods": pods, "deployments": deployments}


def start_background_poller(namespace: str = DEFAULT_NAMESPACE):
    """Run collect_once() and self-healing scan on a loop in a background
    thread so metrics stay fresh and failed pods are recovered."""
    import os
    from healer import scan_and_heal

    enable_healing = os.environ.get("ENABLE_SELF_HEALING", "true").lower() in (
        "true",
        "1",
        "yes",
    )

    def loop():
        while True:
            try:
                collect_once(namespace)
                if enable_healing:
                    core, _ = get_clients()
                    scan_and_heal(core, namespace)
            except Exception:  # noqa: BLE001
                logger.exception("monitor / healer poll failed")
            time.sleep(POLL_INTERVAL_SECONDS)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return thread

