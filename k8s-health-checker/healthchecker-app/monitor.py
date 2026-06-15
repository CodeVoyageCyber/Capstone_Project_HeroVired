"""
Health monitoring module.

Polls the Kubernetes API for the GratitudeApp namespace and:
  - exposes Prometheus gauges for node readiness, pod restarts, and
    deployment replica availability
  - provides plain-Python summaries used by the FastAPI routes
"""

import logging
import threading
import time

from prometheus_client import Gauge

from k8s_client import get_clients, list_deployments, list_nodes, list_pods

logger = logging.getLogger("monitor")

# Prometheus metrics
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

DEFAULT_NAMESPACE = "default"
POLL_INTERVAL_SECONDS = 15


def collect_once(namespace: str = DEFAULT_NAMESPACE):
    """Fetch current cluster state, update Prometheus metrics, and
    return a JSON-friendly summary."""
    core, apps = get_clients()

    nodes = list_nodes(core)
    pods = list_pods(core, namespace)
    deployments = list_deployments(apps, namespace)

    for node in nodes:
        NODE_READY.labels(node=node["name"]).set(1 if node["ready"] == "True" else 0)

    for pod in pods:
        POD_RESTARTS.labels(namespace=pod["namespace"], pod=pod["name"]).set(
            pod["restarts"]
        )
        POD_PHASE.labels(namespace=pod["namespace"], pod=pod["name"]).set(
            1 if pod["phase"] == "Running" else 0
        )

    for dep in deployments:
        DEPLOYMENT_AVAILABLE.labels(
            namespace=dep["namespace"], deployment=dep["name"]
        ).set(dep["available"])
        DEPLOYMENT_DESIRED.labels(
            namespace=dep["namespace"], deployment=dep["name"]
        ).set(dep["desired"] or 0)

    return {"nodes": nodes, "pods": pods, "deployments": deployments}


def start_background_poller(namespace: str = DEFAULT_NAMESPACE):
    """Run collect_once() on a loop in a background thread so
    Prometheus metrics stay fresh between API calls."""

    def loop():
        while True:
            try:
                collect_once(namespace)
            except Exception:  # noqa: BLE001
                logger.exception("monitor poll failed")
            time.sleep(POLL_INTERVAL_SECONDS)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return thread
