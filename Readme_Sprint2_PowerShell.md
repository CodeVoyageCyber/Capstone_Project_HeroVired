# Sprint 2 — Health Monitoring Module (Windows PowerShell Guide)

**Goal:** Deepen the health-checker's visibility into GratitudeApp's cluster
state — richer per-pod readiness conditions, per-deployment replica health,
new Prometheus metrics, a Grafana dashboard, and Alertmanager rules that fire
on real failure thresholds.

Sprint 2 builds directly on top of Sprint 1. The EKS cluster must already be
running before you start here. All commands below run in **Windows PowerShell
5.1** or **PowerShell 7+ (pwsh)**.

> **Line continuation:** PowerShell uses the backtick `` ` `` where bash uses `\`.
> **Background jobs:** Use `Start-Job { ... }` where bash uses `cmd &`.
> **HTTP calls:** Use `Invoke-RestMethod` / `Invoke-WebRequest` instead of `curl`.

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
| Alertmanager | no rules | 7 rules across node, pod, and deployment groups |

File layout after Sprint 2:

```
k8s-health-checker\
├── healthchecker-app\
│   ├── main.py          ← add /api/health-summary
│   ├── monitor.py       ← add 6 new Prometheus gauges
│   ├── k8s_client.py    ← return pod conditions + node pressure conditions
│   ├── requirements.txt  (unchanged)
│   └── Dockerfile        (unchanged)
├── deploy\
│   ├── healthchecker\
│   │   ├── deployment.yaml  (unchanged)
│   │   └── rbac.yaml        (unchanged)
│   ├── prometheus\
│   │   └── prometheus-values.yaml  ← add dashboard sidecar config
│   └── monitoring\              ← NEW folder
│       ├── prometheus-rules.yaml    ← NEW
│       └── grafana-dashboard-cm.yaml ← NEW
```

---

## 2. Extend k8s_client.py — Richer Data

### Step 2.1 — Open the file in your editor

```powershell
code k8s-health-checker\healthchecker-app\k8s_client.py
# or
notepad k8s-health-checker\healthchecker-app\k8s_client.py
```

### Step 2.2 — Replace the entire file contents with the following

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

### Step 2.3 — Confirm the save

```powershell
Select-String -Path k8s-health-checker\healthchecker-app\k8s_client.py `
  -Pattern "memory_pressure"
# Expected: a matching line — confirms the new field is present
```

---

## 3. Extend monitor.py — New Metrics

**New Prometheus gauges added in Sprint 2:**

| Metric | Meaning |
|---|---|
| `healthchecker_pod_ready` | 1 if pod Ready condition is True |
| `healthchecker_deployment_healthy` | 1 if available ≥ desired |
| `healthchecker_node_memory_pressure` | 1 if MemoryPressure is True |
| `healthchecker_node_disk_pressure` | 1 if DiskPressure is True |
| `healthchecker_node_pid_pressure` | 1 if PIDPressure is True |
| `healthchecker_pod_not_running` | 1 if pod phase is NOT Running |

### Step 3.1 — Open the file

```powershell
code k8s-health-checker\healthchecker-app\monitor.py
```

### Step 3.2 — Replace the entire file contents with the following

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
    core, apps = get_clients()

    nodes       = list_nodes(core)
    pods        = list_pods(core, namespace)
    deployments = list_deployments(apps, namespace)

    for node in nodes:
        n = node["name"]
        NODE_READY.labels(node=n).set(1 if node["ready"] == "True" else 0)
        NODE_MEMORY_PRESSURE.labels(node=n).set(1 if node["memory_pressure"] else 0)
        NODE_DISK_PRESSURE.labels(node=n).set(1 if node["disk_pressure"] else 0)
        NODE_PID_PRESSURE.labels(node=n).set(1 if node["pid_pressure"] else 0)

    for pod in pods:
        ns, name = pod["namespace"], pod["name"]
        POD_RESTARTS.labels(namespace=ns, pod=name).set(pod["restarts"])
        is_running = pod["phase"] == "Running"
        POD_PHASE.labels(namespace=ns, pod=name).set(1 if is_running else 0)
        POD_READY.labels(namespace=ns, pod=name).set(1 if pod["ready"] else 0)
        POD_NOT_RUNNING.labels(namespace=ns, pod=name).set(0 if is_running else 1)

    for dep in deployments:
        ns, name = dep["namespace"], dep["name"]
        DEPLOYMENT_AVAILABLE.labels(namespace=ns, deployment=name).set(dep["available"])
        DEPLOYMENT_DESIRED.labels(namespace=ns, deployment=name).set(dep["desired"])
        DEPLOYMENT_HEALTHY.labels(namespace=ns, deployment=name).set(
            1 if dep["healthy"] else 0
        )

    return {"nodes": nodes, "pods": pods, "deployments": deployments}


def start_background_poller(namespace: str = DEFAULT_NAMESPACE):
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

### Step 4.1 — Open the file

```powershell
code k8s-health-checker\healthchecker-app\main.py
```

### Step 4.2 — Replace the entire file contents with the following

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
    """Aggregate cluster health: healthy | degraded | critical."""
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

### Step 5.1 — Create the monitoring folder

```powershell
New-Item -ItemType Directory -Force k8s-health-checker\deploy\monitoring
```

### Step 5.2 — Create the PrometheusRule file

```powershell
code k8s-health-checker\deploy\monitoring\prometheus-rules.yaml
# or
notepad k8s-health-checker\deploy\monitoring\prometheus-rules.yaml
```

Paste the following content and save:

```yaml
# k8s-health-checker/deploy/monitoring/prometheus-rules.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: gratitudeapp-health-rules
  namespace: monitoring
  labels:
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

### Step 5.3 — Confirm the file was created

```powershell
Test-Path k8s-health-checker\deploy\monitoring\prometheus-rules.yaml
# Expected: True
```

---

## 6. Add Grafana Dashboard via ConfigMap

The Grafana sidecar (enabled in Step 7) watches for ConfigMaps labelled
`grafana_dashboard: "1"` in any namespace and auto-provisions them as dashboards.

### Step 6.1 — Create the ConfigMap file

```powershell
code k8s-health-checker\deploy\monitoring\grafana-dashboard-cm.yaml
```

Paste the following content and save:

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
          "id": 1, "type": "stat", "title": "Nodes Ready",
          "gridPos": { "x": 0, "y": 0, "w": 4, "h": 4 },
          "fieldConfig": { "defaults": { "thresholds": { "mode": "absolute",
            "steps": [{ "color": "red", "value": 0 }, { "color": "green", "value": 1 }] } } },
          "targets": [{ "expr": "sum(healthchecker_node_ready)", "legendFormat": "Ready nodes" }]
        },
        {
          "id": 2, "type": "stat", "title": "Pods Running",
          "gridPos": { "x": 4, "y": 0, "w": 4, "h": 4 },
          "fieldConfig": { "defaults": { "thresholds": { "mode": "absolute",
            "steps": [{ "color": "red", "value": 0 }, { "color": "yellow", "value": 5 }, { "color": "green", "value": 9 }] } } },
          "targets": [{ "expr": "sum(healthchecker_pod_phase_running{namespace='default'})", "legendFormat": "Running pods" }]
        },
        {
          "id": 3, "type": "stat", "title": "Deployments Healthy",
          "gridPos": { "x": 8, "y": 0, "w": 4, "h": 4 },
          "fieldConfig": { "defaults": { "thresholds": { "mode": "absolute",
            "steps": [{ "color": "red", "value": 0 }, { "color": "green", "value": 9 }] } } },
          "targets": [{ "expr": "sum(healthchecker_deployment_healthy{namespace='default'})", "legendFormat": "Healthy deployments" }]
        },
        {
          "id": 4, "type": "stat", "title": "Total Pod Restarts",
          "gridPos": { "x": 12, "y": 0, "w": 4, "h": 4 },
          "fieldConfig": { "defaults": { "thresholds": { "mode": "absolute",
            "steps": [{ "color": "green", "value": 0 }, { "color": "yellow", "value": 5 }, { "color": "red", "value": 10 }] } } },
          "targets": [{ "expr": "sum(healthchecker_pod_restarts_total{namespace='default'})", "legendFormat": "Total restarts" }]
        },
        {
          "id": 5, "type": "timeseries", "title": "Node Readiness Over Time",
          "gridPos": { "x": 0, "y": 4, "w": 12, "h": 8 },
          "targets": [{ "expr": "healthchecker_node_ready", "legendFormat": "{{ node }}" }]
        },
        {
          "id": 6, "type": "timeseries", "title": "Pod Restart Rate — GratitudeApp",
          "gridPos": { "x": 12, "y": 4, "w": 12, "h": 8 },
          "targets": [{ "expr": "healthchecker_pod_restarts_total{namespace='default'}", "legendFormat": "{{ pod }}" }]
        },
        {
          "id": 7, "type": "table", "title": "Deployment Replica Status",
          "gridPos": { "x": 0, "y": 12, "w": 12, "h": 8 },
          "targets": [
            { "expr": "healthchecker_deployment_available_replicas{namespace='default'}", "legendFormat": "available — {{ deployment }}", "instant": true },
            { "expr": "healthchecker_deployment_desired_replicas{namespace='default'}", "legendFormat": "desired — {{ deployment }}", "instant": true }
          ]
        },
        {
          "id": 8, "type": "timeseries", "title": "Node Pressure Conditions",
          "gridPos": { "x": 12, "y": 12, "w": 12, "h": 8 },
          "targets": [
            { "expr": "healthchecker_node_memory_pressure", "legendFormat": "MemoryPressure — {{ node }}" },
            { "expr": "healthchecker_node_disk_pressure",   "legendFormat": "DiskPressure — {{ node }}" },
            { "expr": "healthchecker_node_pid_pressure",    "legendFormat": "PIDPressure — {{ node }}" }
          ]
        }
      ]
    }
```

### Step 6.2 — Confirm both monitoring files exist

```powershell
Get-ChildItem k8s-health-checker\deploy\monitoring\
# Expected:
# prometheus-rules.yaml
# grafana-dashboard-cm.yaml
```

---

## 7. Update prometheus-values.yaml — Dashboard Sidecar

The Grafana sidecar must be enabled so it auto-provisions dashboards from
ConfigMaps labelled `grafana_dashboard: "1"`.

### Step 7.1 — Open the file

```powershell
code k8s-health-checker\deploy\prometheus\prometheus-values.yaml
```

### Step 7.2 — Merge the sidecar block into the existing `grafana:` section

The file already has a `grafana:` block from Sprint 1. Find it and update it
so the complete `grafana:` section looks exactly like this:

```yaml
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
  sidecar:
    dashboards:
      enabled: true
      label: grafana_dashboard
      searchNamespace: ALL
```

> **Important:** Do **not** add a second `grafana:` key. Merge the `sidecar:`
> block into the existing one. Save the file when done.

### Step 7.3 — Confirm the sidecar key is present

```powershell
Select-String -Path k8s-health-checker\deploy\prometheus\prometheus-values.yaml `
  -Pattern "sidecar"
# Expected: a line containing "sidecar:"
```

---

## 8. Rebuild and Redeploy the Health-Checker Image

After editing the three Python files, rebuild the image and push a new version
to ECR, then perform a rolling restart of the running deployment.

### Step 8.1 — Set environment variables

```powershell
$env:AWS_REGION = "us-east-1"
$env:REPO_NAME  = "gratitude-health-checker"
$env:ACCOUNT_ID = aws sts get-caller-identity --query Account --output text
$env:ECR_URI    = "$($env:ACCOUNT_ID).dkr.ecr.$($env:AWS_REGION).amazonaws.com/$($env:REPO_NAME)"

Write-Host "Pushing to: $($env:ECR_URI):latest"
```

### Step 8.2 — Re-authenticate Docker to ECR

```powershell
$loginPassword = aws ecr get-login-password --region $env:AWS_REGION
$loginPassword | docker login `
  --username AWS `
  --password-stdin "$($env:ACCOUNT_ID).dkr.ecr.$($env:AWS_REGION).amazonaws.com"
# Expected: Login Succeeded
```

### Step 8.3 — Build the updated image

```powershell
docker build -t "$($env:REPO_NAME):latest" k8s-health-checker\healthchecker-app\
```

### Step 8.4 — Tag and push to ECR

```powershell
docker tag "$($env:REPO_NAME):latest" "$($env:ECR_URI):latest"
docker push "$($env:ECR_URI):latest"
```

### Step 8.5 — Rolling restart the deployment

```powershell
kubectl rollout restart deployment/health-checker-deployment -n default
```

### Step 8.6 — Watch the rollout complete

```powershell
kubectl rollout status deployment/health-checker-deployment -n default
# Expected: successfully rolled out
```

### Step 8.7 — Confirm the new pod is running

```powershell
kubectl get pods -n default -l component=health-checker
# Expected: 1/1 Running with a recent AGE (seconds or a minute)
```

---

## 9. Apply the New Kubernetes Manifests

Run the following PowerShell commands in order (equivalent of `04-deploy-sprint2.sh`).

### Step 9.1 — Apply the PrometheusRule

```powershell
kubectl apply -f k8s-health-checker\deploy\monitoring\prometheus-rules.yaml
# Expected: prometheusrule.monitoring.coreos.com/gratitudeapp-health-rules created
```

### Step 9.2 — Apply the Grafana dashboard ConfigMap

```powershell
kubectl apply -f k8s-health-checker\deploy\monitoring\grafana-dashboard-cm.yaml
# Expected: configmap/gratitudeapp-health-dashboard created
```

### Step 9.3 — Helm upgrade (enables the Grafana sidecar)

```powershell
helm upgrade monitoring prometheus-community/kube-prometheus-stack `
  --namespace monitoring `
  -f k8s-health-checker\deploy\prometheus\prometheus-values.yaml
```

### Step 9.4 — Wait for monitoring pods to stabilise

```powershell
kubectl wait --for=condition=Ready pods --all -n monitoring --timeout=300s
```

### Step 9.5 — Confirm all resources

```powershell
# PrometheusRule
kubectl get prometheusrule -n monitoring
# Expected: gratitudeapp-health-rules

# Grafana dashboard ConfigMap
kubectl get configmap -n monitoring -l grafana_dashboard=1
# Expected: gratitudeapp-health-dashboard

# All monitoring pods Running
kubectl get pods -n monitoring
```

---

## 10. Verify Everything

Open port-forwards in **separate PowerShell windows**, or run as background
jobs as shown. Give each tunnel ~3 seconds to establish before making requests.

### Step 10.1 — Start port-forwards

**Option A — separate PowerShell windows (recommended):**

```powershell
# Window 1
kubectl port-forward -n default svc/health-checker-cluster-ip-service 8000:8000

# Window 2
kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80

# Window 3
kubectl port-forward -n monitoring svc/monitoring-kube-prometheus-prometheus 9090:9090
```

**Option B — background jobs:**

```powershell
$hcJob   = Start-Job { kubectl port-forward -n default svc/health-checker-cluster-ip-service 8000:8000 }
$grafJob = Start-Job { kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80 }
$promJob = Start-Job { kubectl port-forward -n monitoring svc/monitoring-kube-prometheus-prometheus 9090:9090 }
Start-Sleep -Seconds 3
```

### 10.2 New `/api/health-summary` endpoint

```powershell
Invoke-RestMethod http://localhost:8000/api/health-summary | ConvertTo-Json -Depth 10
```

Expected output on a healthy cluster:

```json
{
    "status":  "healthy",
    "issue_count":  0,
    "issues":  [],
    "nodes_total":  2,
    "pods_total":  10,
    "deployments_total":  9
}
```

Expected output when a pod is degraded:

```json
{
    "status":  "degraded",
    "issue_count":  1,
    "issues":  [
        {
            "severity": "degraded",
            "object": "pod",
            "name": "moods-service-deployment-xxx",
            "reason": "Pending",
            "message": ""
        }
    ],
    "nodes_total":  2,
    "pods_total":  10,
    "deployments_total":  9
}
```

### 10.3 Verify new Prometheus metrics

```powershell
# Filter for the new pod_ready metric
$raw = (Invoke-WebRequest http://localhost:8000/metrics -UseBasicParsing).Content
$raw -split "`n" | Where-Object { $_ -match "healthchecker_pod_ready" }
# Expected:
# healthchecker_pod_ready{namespace="default",pod="client-deployment-xxx"} 1.0
# healthchecker_pod_ready{namespace="default",pod="postgres-deployment-xxx"} 1.0

# Deployment healthy metric
$raw -split "`n" | Where-Object { $_ -match "healthchecker_deployment_healthy" }
# Expected:
# healthchecker_deployment_healthy{deployment="api-gateway-deployment",namespace="default"} 1.0

# Node pressure metrics (all 0.0 on a healthy cluster)
$raw -split "`n" | Where-Object { $_ -match "healthchecker_node_memory_pressure" }
# Expected: healthchecker_node_memory_pressure{node="ip-..."} 0.0
```

Full list of all 11 metric families:

```powershell
$raw = (Invoke-WebRequest http://localhost:8000/metrics -UseBasicParsing).Content
$raw -split "`n" |
    Where-Object { $_ -match "^healthchecker" } |
    ForEach-Object { ($_ -split '\{')[0] } |
    Sort-Object -Unique
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

### 10.4 Verify PrometheusRule is loaded

```powershell
# Check resource was created
kubectl get prometheusrule -n monitoring
# Expected:
# NAME                        AGE
# gratitudeapp-health-rules   1m

# Open Prometheus rules page in browser
Start-Process "http://localhost:9090/rules"
# Look for groups: gratitudeapp.nodes / gratitudeapp.pods / gratitudeapp.deployments
```

### 10.5 Trigger a test alert (optional but recommended)

Scale a deployment to 0 to force the `DeploymentZeroReplicas` alert to fire:

```powershell
# Scale moods-api to 0 replicas
kubectl scale deployment moods-api-deployment --replicas=0 -n default

# Wait ~1 minute, then open the Prometheus alerts page
Start-Sleep -Seconds 65
Start-Process "http://localhost:9090/alerts"
# DeploymentUnavailable and DeploymentZeroReplicas should appear as Firing

# Restore the deployment
kubectl scale deployment moods-api-deployment --replicas=1 -n default
kubectl wait --for=condition=Ready pods -l component=moods-api -n default --timeout=60s
```

### 10.6 Verify Grafana dashboard

```powershell
Start-Process "http://localhost:3000"
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

If the dashboard does not appear within 60 seconds, check the sidecar logs:

```powershell
kubectl logs -n monitoring `
  -l app.kubernetes.io/name=grafana `
  -c grafana-sc-dashboard |
  Select-Object -Last 20
# Look for: "Configmap added" or "dashboard provisioned"
```

### 10.7 Stop background jobs when done

```powershell
Get-Job | Stop-Job
Get-Job | Remove-Job
```

---

## 11. Sprint 2 Deliverables Checklist

- [ ] `k8s_client.py` — `list_nodes` returns `memory_pressure`, `disk_pressure`, `pid_pressure`
- [ ] `k8s_client.py` — `list_pods` returns `ready` (bool), `conditions` dict, `message`
- [ ] `k8s_client.py` — `list_deployments` returns `healthy` (bool)
- [ ] `monitor.py` — 6 new Prometheus gauges registered and updated every 15 s
- [ ] `main.py` — `/api/health-summary` returns `status`, `issues`, and counts
- [ ] Docker image rebuilt and pushed to ECR (`docker push` completed successfully)
- [ ] `kubectl rollout status` shows rollout complete for `health-checker-deployment`
- [ ] `Invoke-RestMethod http://localhost:8000/api/health-summary` returns `status: healthy`
- [ ] All 11 `healthchecker_*` metric families visible at `/metrics`
- [ ] `kubectl get prometheusrule -n monitoring` shows `gratitudeapp-health-rules`
- [ ] Prometheus `/rules` page shows all 7 alert rules loaded
- [ ] Scaling a deployment to 0 triggers `DeploymentZeroReplicas` alert within ~1 minute
- [ ] `kubectl get configmap -n monitoring -l grafana_dashboard=1` shows the dashboard ConfigMap
- [ ] Grafana shows **"GratitudeApp — Cluster Health"** with all 8 panels populated
