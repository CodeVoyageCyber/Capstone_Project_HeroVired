"""
GratitudeApp Health Checker and Auto-Healing — main FastAPI app.

Endpoints:
  - /healthz             liveness check for this app itself
  - /metrics             Prometheus metrics (scraped by the
                         kube-prometheus-stack)
  - /api/nodes           list cluster nodes and Ready status
  - /api/pods            list pods in the target namespace (default:
                         GratitudeApp's "default" namespace)
  - /api/deployments     list deployments and replica availability

Sprint 1 scope is read-only monitoring; self-healing actions are added
in Sprint 3.
"""

import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from k8s_client import get_clients, list_deployments, list_nodes, list_pods
from monitor import collect_once, start_background_poller

TARGET_NAMESPACE = os.environ.get("TARGET_NAMESPACE", "default")

app = FastAPI(
    title="GratitudeApp Health Checker",
    description="Automated health monitoring and self-healing for the GratitudeApp Kubernetes deployment",
    version="0.1.0",
)


@app.on_event("startup")
def on_startup():
    start_background_poller(TARGET_NAMESPACE)


@app.get("/healthz")
def healthz():
    """Basic liveness probe."""
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    """Prometheus metrics endpoint."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/nodes")
def get_nodes():
    """List all nodes in the cluster and their Ready status."""
    try:
        core, _ = get_clients()
        return {"nodes": list_nodes(core)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/pods")
def get_pods(namespace: str = TARGET_NAMESPACE):
    """List pods in the given namespace (default: GratitudeApp namespace)."""
    try:
        core, _ = get_clients()
        return {"pods": list_pods(core, namespace)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/deployments")
def get_deployments(namespace: str = TARGET_NAMESPACE):
    """List deployments and replica availability for the given namespace."""
    try:
        _, apps = get_clients()
        return {"deployments": list_deployments(apps, namespace)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/summary")
def get_summary(namespace: str = TARGET_NAMESPACE):
    """One-shot summary of nodes, pods, and deployments (also updates
    Prometheus metrics immediately)."""
    try:
        return collect_once(namespace)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
