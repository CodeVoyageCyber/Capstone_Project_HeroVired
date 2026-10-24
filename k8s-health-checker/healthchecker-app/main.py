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

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from k8s_client import get_clients, list_deployments, list_nodes, list_pods
from monitor import collect_once, start_background_poller
from healer import get_healing_audit_log, scan_and_heal
from balancer import get_node_balance_report
from slack_notifier import get_notification_history, send_slack_message

TARGET_NAMESPACE = os.environ.get("TARGET_NAMESPACE", "default")

app = FastAPI(
    title="GratitudeApp Health Checker",
    description="Automated health monitoring, self-healing, resource balancing, and alerting for GratitudeApp",
    version="0.5.0",
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


@app.get("/api/healing-log")
def get_healing_log(limit: int = 50):
    """Structured audit log of all self-healing actions performed."""
    try:
        return {"healing_log": get_healing_audit_log(limit)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/heal")
def trigger_heal(namespace: str = TARGET_NAMESPACE):
    """Trigger an on-demand self-healing scan and recovery."""
    try:
        core, _ = get_clients()
        actions = scan_and_heal(core, namespace)
        return {"status": "ok", "actions_taken": actions}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/node-balancing")
def get_node_balancing(namespace: str = TARGET_NAMESPACE):
    """Inspect and report pod distribution and resource balancing across nodes."""
    try:
        core, _ = get_clients()
        return get_node_balance_report(core, namespace)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/notify/slack")
async def post_slack_notification(request: Request):
    """
    Send an on-demand Slack notification (Block Kit formatted).
    Accepts JSON payload:
      {"title": str, "message": str, "severity": "info"|"warning"|"critical"|"healing", "fields": dict}
    """
    try:
        body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    except Exception:
        body = {}

    title = body.get("title", "Test Alert from GratitudeApp")
    message = body.get("message", "Manual test alert initiated via health-checker API.")
    severity = body.get("severity", "info")
    fields = body.get("fields", {"Source": "Health-Checker API", "Environment": "Kubernetes"})

    result = send_slack_message(
        title=title,
        message=message,
        severity=severity,
        fields=fields,
    )
    return {"status": "ok", "notification": result}


@app.get("/api/notifications")
def get_notifications(limit: int = 50):
    """Retrieve history of recently dispatched alert notifications."""
    try:
        return {"notifications": get_notification_history(limit)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


if __name__ == "__main__":

    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)

