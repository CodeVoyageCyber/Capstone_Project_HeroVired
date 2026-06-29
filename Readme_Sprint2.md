# Sprint 2 — Health Monitoring Module (Node & Pod Checks)

**Goal:** Deepen the health-checker's visibility into GratitudeApp's cluster
state — richer per-pod readiness conditions, per-deployment replica health,
new Prometheus metrics, a Grafana dashboard, and Alertmanager rules that fire
on real failure thresholds.

Sprint 2 builds directly on top of Sprint 1. The cluster must already be
running before you start here.

---

## Table of Contents

1. [What Changes in Sprint 2](#1-what-changes-in-sprint-2)
2. [Extend k8s_client.py — Richer Data](#2-extend-k8s_clientpy--richer-data)
3. [Extend monitor.py — New Metrics](#3-extend-monitorpy--new-metrics)
4. [Extend main.py — Health Summary Endpoint](#4-extend-mainpy--health-summary-endpoint)
5. [Add PrometheusRule — Alert Thresholds](#5-add-prometheusrule--alert-thresholds)
6. [Add Grafana Dashboard via ConfigMap](#6-add-grafana-dashboard-via-configmap)
7. [Update prometheus-values.yaml — Dashboard Sidecar](#7-update-prometheus-valuesyaml--dashboard-sidecar)
8. [Rebuild and Redeploy the Health-Checker Image](#8-rebuild-and-redeploy-the-health-checker-image)
9. [Apply the New Kubernetes Manifests](#9-apply-the-new-kubernetes-manifests)
10. [Verify Everything](#10-verify-everything)
11. [Sprint 2 Deliverables Checklist](#11-sprint-2-deliverables-checklist)

---

## 1. What Changes in Sprint 2

| Area | Sprint 1 | Sprint 2 (added) |
|---|---|---|
| `k8s_client.py` | phase, restarts, node ready | + pod conditions, node pressure conditions |
| `monitor.py` | 5 basic gauges | + 6 new gauges (pod ready, deployment healthy, node pressure) |
| `main.py` | 5 endpoints | + `/api/health-summary` aggregate endpoint |
| K8s manifests | none new | `PrometheusRule` (alert rules), Grafana `ConfigMap` |
| Grafana | no provisioned dashboards | GratitudeApp health dashboard auto-provisioned |
| Alertmanager | no rules | 4 rules: NodeNotReady, PodNotRunning, HighRestarts, DeploymentUnavailable |

File layout after Sprint 2:

```
k8s-health-checker/
├── healthchecker-app/
│   ├── main.py          ← add /api/health-summary
│   ├── monitor.py       ← add 6 new Prometheus gauges + richer collection
│   ├── k8s_client.py    ← return pod conditions + node pressure conditions
│   ├── requirements.txt (unchanged)
│   └── Dockerfile       (unchanged)
├── deploy/
│   ├── healthchecker/
│   │   ├── deployment.yaml  (unchanged)
│   │   └── rbac.yaml        (unchanged)
│   ├── prometheus/
│   │   └── prometheus-values.yaml  ← add dashboard sidecar config
│   └── monitoring/              ← NEW folder
│       ├── prometheus-rules.yaml    ← NEW: PrometheusRule CRD
│       └── grafana-dashboard-cm.yaml ← NEW: Grafana dashboard ConfigMap
└── scripts/
    └── 04-deploy-sprint2.sh    ← NEW: one-shot sprint 2 deploy script
```

---

## 2. Extend k8s_client.py — Richer Data

Replace the contents of
`k8s-health-checker/healthchecker-app/k8s_client.py` with the version below.
The key additions are:

- `list_nodes` now returns `memory_pressure`, `disk_pressure`, `pid_pressure`
  booleans alongside `ready`.
- `list_pods` now returns a `conditions` dict (`Ready`, `Initialized`,
  `ContainersReady`, `PodScheduled`) and the `message` field for pods that are
  not Running.

```python
# k8s-health-checker/healthchecker-app/k8s_client.py

from kubernetes import client, config


def get_clients():
    """Return (CoreV1Api, AppsV1Api) clients."""
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()
    return client.CoreV1Api(), client.AppsV1Api()


def list_nodes(core: client.CoreV1Api):
    """Return node name, Ready status, and pressure conditions."""
    nodes = core.list_node()
    result = []
    for node in nodes.items:
        cond_map = {c.type: c.status for c in node.status.conditions}
        result.append({
            "name": node.metadata.name,
            "ready": cond_map.get("Ready", "Unknown"),
            "memory_pressure": cond_map.get("MemoryPressure", "Unknown") == "True",
            "disk_pressure":   cond_map.get("DiskPressure",   "Unknown") == "True",
            "pid_pressure":    cond_map.get("PIDPressure",    "Unknown") == "True",
        })
    return result


def list_pods(core: client.CoreV1Api, namespace: str = "default"):
    """Return pod name, phase, restart count, node, and readiness conditions."""
    pods = core.list_namespaced_pod(namespace)
    result = []
    for pod in pods.items:
        restarts = sum(
            (cs.restart_count or 0)
            for cs in (pod.status.container_statuses or [])
        )
        cond_map = {}
        for c in (pod.status.conditions or []):
            cond_map[c.type] = c.status   # "True" | "False" | "Unknown"

        # capture the message for non-Running pods (useful for alerts)
        message = ""
        for cs in (pod.status.container_statuses or []):
            if cs.state and cs.state.waiting and cs.state.waiting.message:
                message = cs.state.waiting.message
                break

        result.append({
            "name":       pod.metadata.name,
            "namespace":  pod.metadata.namespace,
            "phase":      pod.status.phase,
            "restarts":   restarts,
            "node":       pod.spec.node_name,
            "ready":      cond_map.get("Ready", "False") == "True",
            "conditions": cond_map,
            "message":    message,
        })
    return result


def list_deployments(apps: client.AppsV1Api, namespace: str = "default"):
    """Return deployment name, desired vs available replica counts, and health flag."""
    deployments = apps.list_namespaced_deployment(namespace)
    result = []
    for dep in deployments.items:
        desired   = dep.spec.replicas or 0
        available = dep.status.available_replicas or 0
        ready     = dep.status.ready_replicas or 0
        result.append({
            "name":      dep.metadata.name,
            "namespace": dep.metadata.namespace,
            "desired":   desired,
            "available": available,
            "ready":     ready,
            "healthy":   available >= desired and desired > 0,
        })
    return result
```

---

## 3. Extend monitor.py — New Metrics

Replace the contents of
`k8s-health-checker/healthchecker-app/monitor.py` with the version below.

**New Prometheus gauges added:**

| Metric | Labels | Meaning |
|---|---|---|
| `healthchecker_pod_ready` | namespace, pod | 1 if pod Ready condition is True |
| `healthchecker_deployment_healthy` | namespace, deployment | 1 if available ≥ desired |
| `healthchecker_node_memory_pressure` | node | 1 if MemoryPressure condition is True |
| `healthchecker_node_disk_pressure` | node | 1 if DiskPressure condition is True |
| `healthchecker_node_pid_pressure` | node | 1 if PIDPressure condition is True |
| `healthchecker_pod_not_running` | namespace, pod | 1 if pod phase is NOT Running |

```python
# k8s-health-checker/healthchecker-app/monitor.py

import logging
import threading
import time

from prometheus_client import Gauge

from k8s_client import get_clients, list_deployments, list_nodes, list_pods

logger = logging.getLogger("monitor")

# ── Sprint 1 metrics (kept as-is) ────────────────────────────────────────────
NODE_READY = Gauge(
    "healthchecker_node_ready",
    "1 if node is Ready, 0 otherwise",
    ["node"],
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

# ── Sprint 2 metrics (new) ────────────────────────────────────────────────────
POD_READY = Gauge(
    "healthchecker_pod_ready",
    "1 if pod Ready condition is True, 0 otherwise",
    ["namespace", "pod"],
)
DEPLOYMENT_HEALTHY = Gauge(
    "healthchecker_deployment_healthy",
    "1 if available replicas >= desired replicas and desired > 0",
    ["namespace", "deployment"],
)
NODE_MEMORY_PRESSURE = Gauge(
    "healthchecker_node_memory_pressure",
    "1 if node MemoryPressure condition is True",
    ["node"],
)
NODE_DISK_PRESSURE = Gauge(
    "healthchecker_node_disk_pressure",
    "1 if node DiskPressure condition is True",
    ["node"],
)
NODE_PID_PRESSURE = Gauge(
    "healthchecker_node_pid_pressure",
    "1 if node PIDPressure condition is True",
    ["node"],
)
POD_NOT_RUNNING = Gauge(
    "healthchecker_pod_not_running",
    "1 if pod phase is not Running (Pending/Failed/Unknown)",
    ["namespace", "pod"],
)

DEFAULT_NAMESPACE = "default"
POLL_INTERVAL_SECONDS = 15


def collect_once(namespace: str = DEFAULT_NAMESPACE) -> dict:
    """Fetch current cluster state, update all Prometheus metrics, and
    return a JSON-friendly summary including the new Sprint 2 fields."""
    core, apps = get_clients()

    nodes       = list_nodes(core)
    pods        = list_pods(core, namespace)
    deployments = list_deployments(apps, namespace)

    # ── node metrics ──────────────────────────────────────────────────────────
    for node in nodes:
        n = node["name"]
        NODE_READY.labels(node=n).set(1 if node["ready"] == "True" else 0)
        NODE_MEMORY_PRESSURE.labels(node=n).set(1 if node["memory_pressure"] else 0)
        NODE_DISK_PRESSURE.labels(node=n).set(1 if node["disk_pressure"] else 0)
        NODE_PID_PRESSURE.labels(node=n).set(1 if node["pid_pressure"] else 0)

    # ── pod metrics ───────────────────────────────────────────────────────────
    for pod in pods:
        ns, name = pod["namespace"], pod["name"]
        POD_RESTARTS.labels(namespace=ns, pod=name).set(pod["restarts"])
        is_running = pod["phase"] == "Running"
        POD_PHASE.labels(namespace=ns, pod=name).set(1 if is_running else 0)
        POD_READY.labels(namespace=ns, pod=name).set(1 if pod["ready"] else 0)
        POD_NOT_RUNNING.labels(namespace=ns, pod=name).set(0 if is_running else 1)

    # ── deployment metrics ────────────────────────────────────────────────────
    for dep in deployments:
        ns, name = dep["namespace"], dep["name"]
        DEPLOYMENT_AVAILABLE.labels(namespace=ns, deployment=name).set(dep["available"])
        DEPLOYMENT_DESIRED.labels(namespace=ns, deployment=name).set(dep["desired"])
        DEPLOYMENT_HEALTHY.labels(namespace=ns, deployment=name).set(
            1 if dep["healthy"] else 0
        )

    return {"nodes": nodes, "pods": pods, "deployments": deployments}


def start_background_poller(namespace: str = DEFAULT_NAMESPACE):
    """Run collect_once() on a background thread every POLL_INTERVAL_SECONDS."""
    def loop():
        while True:
            try:
                collect_once(namespace)
            except Exception:
                logger.exception("monitor poll failed")
            time.sleep(POLL_INTERVAL_SECONDS)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return thread
```

---

## 4. Extend main.py — Health Summary Endpoint

Add a `/api/health-summary` endpoint that returns a single aggregate status
(`healthy` / `degraded` / `critical`) plus a list of active issues.

Replace the contents of `k8s-health-checker/healthchecker-app/main.py`:

```python
# k8s-health-checker/healthchecker-app/main.py

import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from k8s_client import get_clients, list_deployments, list_nodes, list_pods
from monitor import collect_once, start_background_poller

TARGET_NAMESPACE = os.environ.get("TARGET_NAMESPACE", "default")

app = FastAPI(
    title="GratitudeApp Health Checker",
    description="Automated health monitoring and self-healing for GratitudeApp on EKS",
    version="0.2.0",
)


@app.on_event("startup")
def on_startup():
    start_background_poller(TARGET_NAMESPACE)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/nodes")
def get_nodes():
    try:
        core, _ = get_clients()
        return {"nodes": list_nodes(core)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/pods")
def get_pods(namespace: str = TARGET_NAMESPACE):
    try:
        core, _ = get_clients()
        return {"pods": list_pods(core, namespace)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/deployments")
def get_deployments(namespace: str = TARGET_NAMESPACE):
    try:
        _, apps = get_clients()
        return {"deployments": list_deployments(apps, namespace)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/summary")
def get_summary(namespace: str = TARGET_NAMESPACE):
    try:
        return collect_once(namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/health-summary")
def get_health_summary(namespace: str = TARGET_NAMESPACE):
    """Aggregate cluster health: healthy | degraded | critical.

    Rules:
      critical  — any node not Ready, OR any deployment with 0 available replicas
      degraded  — any pod not Running, OR any deployment under-replicated,
                  OR any node under pressure
      healthy   — everything nominal
    """
    try:
        data   = collect_once(namespace)
        issues = []

        for node in data["nodes"]:
            if node["ready"] != "True":
                issues.append({"severity": "critical", "object": "node",
                                "name": node["name"], "reason": "NotReady"})
            if node["memory_pressure"]:
                issues.append({"severity": "degraded", "object": "node",
                                "name": node["name"], "reason": "MemoryPressure"})
            if node["disk_pressure"]:
                issues.append({"severity": "degraded", "object": "node",
                                "name": node["name"], "reason": "DiskPressure"})
            if node["pid_pressure"]:
                issues.append({"severity": "degraded", "object": "node",
                                "name": node["name"], "reason": "PIDPressure"})

        for pod in data["pods"]:
            if pod["phase"] != "Running":
                issues.append({"severity": "degraded", "object": "pod",
                                "name": pod["name"], "reason": pod["phase"],
                                "message": pod.get("message", "")})
            if pod["restarts"] >= 5:
                issues.append({"severity": "degraded", "object": "pod",
                                "name": pod["name"],
                                "reason": f"HighRestarts({pod['restarts']})"})

        for dep in data["deployments"]:
            if dep["available"] == 0 and dep["desired"] > 0:
                issues.append({"severity": "critical", "object": "deployment",
                                "name": dep["name"], "reason": "ZeroReplicas"})
            elif not dep["healthy"]:
                issues.append({"severity": "degraded", "object": "deployment",
                                "name": dep["name"],
                                "reason": f"UnderReplicated({dep['available']}/{dep['desired']})"})

        if any(i["severity"] == "critical" for i in issues):
            overall = "critical"
        elif issues:
            overall = "degraded"
        else:
            overall = "healthy"

        return {
            "status": overall,
            "issue_count": len(issues),
            "issues": issues,
            "nodes_total":       len(data["nodes"]),
            "pods_total":        len(data["pods"]),
            "deployments_total": len(data["deployments"]),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
```

---

## 5. Add PrometheusRule — Alert Thresholds

Create the file
`k8s-health-checker/deploy/monitoring/prometheus-rules.yaml`:

```bash
mkdir -p k8s-health-checker/deploy/monitoring
```

```yaml
# k8s-health-checker/deploy/monitoring/prometheus-rules.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: gratitudeapp-health-rules
  namespace: monitoring
  labels:
    # kube-prometheus-stack picks up rules with this label
    release: monitoring
spec:
  groups:
    - name: gratitudeapp.nodes
      interval: 30s
      rules:
        - alert: NodeNotReady
          expr: healthchecker_node_ready == 0
          for: 2m
          labels:
            severity: critical
          annotations:
            summary: "Node {{ $labels.node }} is NOT Ready"
            description: >
              Node {{ $labels.node }} has been in a NotReady state for more
              than 2 minutes. Manual investigation or node replacement may
              be required.

        - alert: NodeMemoryPressure
          expr: healthchecker_node_memory_pressure == 1
          for: 2m
          labels:
            severity: warning
          annotations:
            summary: "Node {{ $labels.node }} is under memory pressure"
            description: >
              Node {{ $labels.node }} has reported MemoryPressure for over
              2 minutes. Consider scaling the node group or reducing pod
              memory usage.

        - alert: NodeDiskPressure
          expr: healthchecker_node_disk_pressure == 1
          for: 2m
          labels:
            severity: warning
          annotations:
            summary: "Node {{ $labels.node }} is under disk pressure"
            description: >
              Node {{ $labels.node }} has reported DiskPressure for over
              2 minutes. Clean up unused images or expand the root volume.

    - name: gratitudeapp.pods
      interval: 30s
      rules:
        - alert: PodNotRunning
          expr: healthchecker_pod_not_running{namespace="default"} == 1
          for: 5m
          labels:
            severity: warning
          annotations:
            summary: "Pod {{ $labels.pod }} is not Running"
            description: >
              Pod {{ $labels.pod }} in namespace {{ $labels.namespace }} has
              not been in the Running phase for more than 5 minutes.
              Check logs: kubectl logs {{ $labels.pod }} -n {{ $labels.namespace }}

        - alert: PodHighRestartCount
          expr: healthchecker_pod_restarts_total{namespace="default"} > 5
          for: 1m
          labels:
            severity: warning
          annotations:
            summary: "Pod {{ $labels.pod }} has restarted {{ $value }} times"
            description: >
              Pod {{ $labels.pod }} in namespace {{ $labels.namespace }} has
              restarted more than 5 times. Likely a CrashLoopBackOff.
              Check logs: kubectl logs {{ $labels.pod }} -n {{ $labels.namespace }} --previous

        - alert: PodCrashLoopBackOff
          expr: |
            healthchecker_pod_restarts_total{namespace="default"} > 10
            and
            healthchecker_pod_phase_running{namespace="default"} == 0
          for: 2m
          labels:
            severity: critical
          annotations:
            summary: "Pod {{ $labels.pod }} is in CrashLoopBackOff"
            description: >
              Pod {{ $labels.pod }} has >10 restarts and is not Running.
              Self-healing will attempt recovery in Sprint 3.

    - name: gratitudeapp.deployments
      interval: 30s
      rules:
        - alert: DeploymentUnavailable
          expr: healthchecker_deployment_healthy{namespace="default"} == 0
          for: 1m
          labels:
            severity: critical
          annotations:
            summary: "Deployment {{ $labels.deployment }} is unhealthy"
            description: >
              Deployment {{ $labels.deployment }} in namespace
              {{ $labels.namespace }} has fewer available replicas than
              desired for more than 1 minute.
              Check: kubectl describe deployment {{ $labels.deployment }}

        - alert: DeploymentZeroReplicas
          expr: healthchecker_deployment_available_replicas{namespace="default"} == 0
          for: 1m
          labels:
            severity: critical
          annotations:
            summary: "Deployment {{ $labels.deployment }} has ZERO running replicas"
            description: >
              Deployment {{ $labels.deployment }} in namespace
              {{ $labels.namespace }} has 0 available replicas.
              GratitudeApp service is completely down.
```

---

## 6. Add Grafana Dashboard via ConfigMap

Create the file
`k8s-health-checker/deploy/monitoring/grafana-dashboard-cm.yaml`.

The Grafana sidecar (enabled in step 7) watches for ConfigMaps labelled
`grafana_dashboard: "1"` in any namespace and auto-provisions them.

```yaml
# k8s-health-checker/deploy/monitoring/grafana-dashboard-cm.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: gratitudeapp-health-dashboard
  namespace: monitoring
  labels:
    grafana_dashboard: "1"
data:
  gratitudeapp-health.json: |
    {
      "title": "GratitudeApp — Cluster Health",
      "uid": "gratitude-health-sprint2",
      "schemaVersion": 38,
      "refresh": "15s",
      "time": { "from": "now-30m", "to": "now" },
      "panels": [
        {
          "id": 1,
          "type": "stat",
          "title": "Nodes Ready",
          "gridPos": { "x": 0, "y": 0, "w": 4, "h": 4 },
          "fieldConfig": {
            "defaults": {
              "thresholds": {
                "mode": "absolute",
                "steps": [
                  { "color": "red",   "value": 0 },
                  { "color": "green", "value": 1 }
                ]
              }
            }
          },
          "targets": [{
            "expr": "sum(healthchecker_node_ready)",
            "legendFormat": "Ready nodes"
          }]
        },
        {
          "id": 2,
          "type": "stat",
          "title": "Pods Running",
          "gridPos": { "x": 4, "y": 0, "w": 4, "h": 4 },
          "fieldConfig": {
            "defaults": {
              "thresholds": {
                "mode": "absolute",
                "steps": [
                  { "color": "red",    "value": 0 },
                  { "color": "yellow", "value": 5 },
                  { "color": "green",  "value": 9 }
                ]
              }
            }
          },
          "targets": [{
            "expr": "sum(healthchecker_pod_phase_running{namespace='default'})",
            "legendFormat": "Running pods"
          }]
        },
        {
          "id": 3,
          "type": "stat",
          "title": "Deployments Healthy",
          "gridPos": { "x": 8, "y": 0, "w": 4, "h": 4 },
          "fieldConfig": {
            "defaults": {
              "thresholds": {
                "mode": "absolute",
                "steps": [
                  { "color": "red",   "value": 0 },
                  { "color": "green", "value": 9 }
                ]
              }
            }
          },
          "targets": [{
            "expr": "sum(healthchecker_deployment_healthy{namespace='default'})",
            "legendFormat": "Healthy deployments"
          }]
        },
        {
          "id": 4,
          "type": "stat",
          "title": "Total Pod Restarts",
          "gridPos": { "x": 12, "y": 0, "w": 4, "h": 4 },
          "fieldConfig": {
            "defaults": {
              "thresholds": {
                "mode": "absolute",
                "steps": [
                  { "color": "green", "value": 0 },
                  { "color": "yellow","value": 5 },
                  { "color": "red",   "value": 10 }
                ]
              }
            }
          },
          "targets": [{
            "expr": "sum(healthchecker_pod_restarts_total{namespace='default'})",
            "legendFormat": "Total restarts"
          }]
        },
        {
          "id": 5,
          "type": "timeseries",
          "title": "Node Readiness Over Time",
          "gridPos": { "x": 0, "y": 4, "w": 12, "h": 8 },
          "targets": [{
            "expr": "healthchecker_node_ready",
            "legendFormat": "{{ node }}"
          }]
        },
        {
          "id": 6,
          "type": "timeseries",
          "title": "Pod Restart Rate — GratitudeApp",
          "gridPos": { "x": 12, "y": 4, "w": 12, "h": 8 },
          "targets": [{
            "expr": "healthchecker_pod_restarts_total{namespace='default'}",
            "legendFormat": "{{ pod }}"
          }]
        },
        {
          "id": 7,
          "type": "table",
          "title": "Deployment Replica Status",
          "gridPos": { "x": 0, "y": 12, "w": 12, "h": 8 },
          "targets": [
            {
              "expr": "healthchecker_deployment_available_replicas{namespace='default'}",
              "legendFormat": "available — {{ deployment }}",
              "instant": true
            },
            {
              "expr": "healthchecker_deployment_desired_replicas{namespace='default'}",
              "legendFormat": "desired — {{ deployment }}",
              "instant": true
            }
          ]
        },
        {
          "id": 8,
          "type": "timeseries",
          "title": "Node Pressure Conditions",
          "gridPos": { "x": 12, "y": 12, "w": 12, "h": 8 },
          "targets": [
            {
              "expr": "healthchecker_node_memory_pressure",
              "legendFormat": "MemoryPressure — {{ node }}"
            },
            {
              "expr": "healthchecker_node_disk_pressure",
              "legendFormat": "DiskPressure — {{ node }}"
            },
            {
              "expr": "healthchecker_node_pid_pressure",
              "legendFormat": "PIDPressure — {{ node }}"
            }
          ]
        }
      ]
    }
```

---

## 7. Update prometheus-values.yaml — Dashboard Sidecar

The Grafana sidecar must be enabled so it watches for ConfigMaps with the
`grafana_dashboard: "1"` label. Append the following block to
`k8s-health-checker/deploy/prometheus/prometheus-values.yaml`:

```yaml
# append to the bottom of prometheus-values.yaml

grafana:
  adminPassword: changeme
  persistence:
    enabled: false
  resources:
    requests:
      cpu: 100m
      memory: 256Mi
    limits:
      cpu: 250m
      memory: 512Mi
  # Enable the sidecar that auto-provisions dashboards from ConfigMaps
  sidecar:
    dashboards:
      enabled: true
      label: grafana_dashboard        # watches ConfigMaps with this label
      searchNamespace: ALL            # look across all namespaces
```

> **Note:** The `grafana:` block already exists in the file from Sprint 1.
> Merge the `sidecar:` section into it — do not duplicate the top-level key.
> The final grafana section should look like the block above in full.

---

## 8. Rebuild and Redeploy the Health-Checker Image

After modifying `k8s_client.py`, `monitor.py`, and `main.py`, rebuild and
push a new image to ECR, then restart the running deployment.

```bash
# Step 1 — rebuild and push (reuses the script from Sprint 1)
./k8s-health-checker/scripts/00-build-and-push-healthchecker.sh

# The script prints:
#   ==> Done. Image pushed to:
#       123456789012.dkr.ecr.us-east-1.amazonaws.com/gratitude-health-checker:latest

# Step 2 — rolling restart the running deployment (pulls the new :latest)
kubectl rollout restart deployment/health-checker-deployment -n default

# Step 3 — watch the rollout until complete
kubectl rollout status deployment/health-checker-deployment -n default
# Expected: successfully rolled out

# Step 4 — confirm new pod is running
kubectl get pods -n default -l component=health-checker
```

---

## 9. Apply the New Kubernetes Manifests

Create a convenience script for Sprint 2 deployment:

```bash
# k8s-health-checker/scripts/04-deploy-sprint2.sh
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Applying PrometheusRule (alert thresholds)..."
kubectl apply -f "$ROOT_DIR/deploy/monitoring/prometheus-rules.yaml"

echo "==> Applying Grafana dashboard ConfigMap..."
kubectl apply -f "$ROOT_DIR/deploy/monitoring/grafana-dashboard-cm.yaml"

echo "==> Upgrading kube-prometheus-stack with updated values (sidecar enabled)..."
helm upgrade monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  -f "$ROOT_DIR/deploy/prometheus/prometheus-values.yaml"

echo "==> Waiting for monitoring pods to stabilise..."
kubectl wait --for=condition=Ready pods --all -n monitoring --timeout=300s || true

echo "==> Sprint 2 manifests applied."
echo ""
echo "Verify alerts:    kubectl get prometheusrule -n monitoring"
echo "Verify dashboard: kubectl get configmap -n monitoring -l grafana_dashboard=1"
```

Make it executable and run it:

```bash
chmod +x k8s-health-checker/scripts/04-deploy-sprint2.sh
./k8s-health-checker/scripts/04-deploy-sprint2.sh
```

Apply manually if you prefer:

```bash
# PrometheusRule
kubectl apply -f k8s-health-checker/deploy/monitoring/prometheus-rules.yaml

# Grafana dashboard ConfigMap
kubectl apply -f k8s-health-checker/deploy/monitoring/grafana-dashboard-cm.yaml

# Helm upgrade (adds sidecar)
helm upgrade monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  -f k8s-health-checker/deploy/prometheus/prometheus-values.yaml
```

---

## 10. Verify Everything

### 10.1 New health-checker endpoints

```bash
# Port-forward (if not already open from Sprint 1)
kubectl port-forward -n default svc/health-checker-cluster-ip-service 8000:8000 &

# New aggregate health summary
curl http://localhost:8000/api/health-summary | python3 -m json.tool
```

Expected output (healthy cluster):
```json
{
    "status": "healthy",
    "issue_count": 0,
    "issues": [],
    "nodes_total": 2,
    "pods_total": 10,
    "deployments_total": 9
}
```

Expected output (degraded — e.g. one pod restarting):
```json
{
    "status": "degraded",
    "issue_count": 1,
    "issues": [
        {
            "severity": "degraded",
            "object": "pod",
            "name": "moods-service-deployment-xxx",
            "reason": "Pending",
            "message": ""
        }
    ],
    "nodes_total": 2,
    "pods_total": 10,
    "deployments_total": 9
}
```

```bash
# Verify new metrics are exposed
curl http://localhost:8000/metrics | grep healthchecker_pod_ready
# Expected lines like:
# healthchecker_pod_ready{namespace="default",pod="client-deployment-xxx"} 1.0
# healthchecker_pod_ready{namespace="default",pod="postgres-deployment-xxx"} 1.0

curl http://localhost:8000/metrics | grep healthchecker_deployment_healthy
# Expected:
# healthchecker_deployment_healthy{deployment="api-gateway-deployment",namespace="default"} 1.0

curl http://localhost:8000/metrics | grep healthchecker_node_memory_pressure
# Expected (no pressure on a healthy cluster):
# healthchecker_node_memory_pressure{node="ip-..."} 0.0
```

### 10.2 PrometheusRule is loaded

```bash
# Check the rule was created
kubectl get prometheusrule -n monitoring
# Expected:
# NAME                          AGE
# gratitudeapp-health-rules     1m

# Check Prometheus has picked up the rule (port-forward Prometheus)
kubectl port-forward -n monitoring svc/monitoring-kube-prometheus-prometheus 9090:9090 &
open http://localhost:9090/rules
# Look for group: gratitudeapp.nodes / gratitudeapp.pods / gratitudeapp.deployments
```

### 10.3 Trigger a test alert (optional)

Force a pod into a failing state to verify the alert fires:

```bash
# Scale a deployment to 0 — triggers DeploymentZeroReplicas alert
kubectl scale deployment moods-api-deployment --replicas=0 -n default

# Wait ~1 minute, then check Prometheus alerts page
open http://localhost:9090/alerts
# DeploymentUnavailable and DeploymentZeroReplicas should appear as Firing

# Restore the deployment
kubectl scale deployment moods-api-deployment --replicas=1 -n default
kubectl wait --for=condition=Ready pods -l component=moods-api -n default --timeout=60s
```

### 10.4 Grafana dashboard

```bash
# Port-forward Grafana (if not already open)
kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80 &
open http://localhost:3000
# Username: admin  |  Password: changeme
```

Steps in Grafana:
1. Go to **Dashboards → Browse**.
2. Find **"GratitudeApp — Cluster Health"** (auto-provisioned from the ConfigMap).
3. Confirm all 8 panels are rendering:
   - Nodes Ready (stat)
   - Pods Running (stat)
   - Deployments Healthy (stat)
   - Total Pod Restarts (stat)
   - Node Readiness Over Time (graph)
   - Pod Restart Rate (graph)
   - Deployment Replica Status (table)
   - Node Pressure Conditions (graph)

If the dashboard does not appear within 60 seconds:

```bash
# Check the sidecar container is running inside the Grafana pod
kubectl get pods -n monitoring -l app.kubernetes.io/name=grafana
kubectl logs -n monitoring -l app.kubernetes.io/name=grafana -c grafana-sc-dashboard | tail -20
# Look for: "Configmap added"
```

### 10.5 Full metrics list

```bash
# All healthchecker metrics at a glance
curl -s http://localhost:8000/metrics | grep "^healthchecker" | awk -F'{' '{print $1}' | sort -u
```

Expected output:
```
healthchecker_deployment_available_replicas
healthchecker_deployment_desired_replicas
healthchecker_deployment_healthy
healthchecker_node_disk_pressure
healthchecker_node_memory_pressure
healthchecker_node_pid_pressure
healthchecker_node_ready
healthchecker_pod_not_running
healthchecker_pod_phase_running
healthchecker_pod_ready
healthchecker_pod_restarts_total
```

---

## 11. Sprint 2 Deliverables Checklist

- [ ] `k8s_client.py` — `list_nodes` returns `memory_pressure`, `disk_pressure`, `pid_pressure`
- [ ] `k8s_client.py` — `list_pods` returns `ready` (bool), `conditions` dict, `message`
- [ ] `k8s_client.py` — `list_deployments` returns `healthy` (bool)
- [ ] `monitor.py` — 6 new Prometheus gauges registered and updated every 15 s
- [ ] `main.py` — `/api/health-summary` returns `status`, `issues`, and counts
- [ ] Health-checker image rebuilt and pushed to ECR with version `0.2.0`
- [ ] `kubectl rollout status` shows rollout complete for `health-checker-deployment`
- [ ] `curl /api/health-summary` returns `{"status": "healthy", ...}` on a clean cluster
- [ ] `curl /metrics` shows all 11 `healthchecker_*` metric families
- [ ] `kubectl get prometheusrule -n monitoring` shows `gratitudeapp-health-rules`
- [ ] Prometheus `/rules` page shows all 7 alert rules loaded (3 node + 3 pod + 2 deployment)
- [ ] Scaling a deployment to 0 triggers `DeploymentZeroReplicas` alert within 1 minute
- [ ] `kubectl get configmap -n monitoring -l grafana_dashboard=1` shows the dashboard ConfigMap
- [ ] Grafana shows **"GratitudeApp — Cluster Health"** dashboard with all 8 panels populated
