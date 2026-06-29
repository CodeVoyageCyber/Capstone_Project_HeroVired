# Sprint 2 — Local minikube Deployment Guide

**Goal:** Apply the Sprint 2 health-monitoring changes (richer metrics,
`/api/health-summary`, PrometheusRules, Grafana dashboard) to a locally
running minikube cluster — no AWS account required.

> **Prerequisite:** Complete the Sprint 1 local guide (`Readme_Local.md` on
> the `sprint1` branch) first. The cluster must be running with GratitudeApp
> and the Sprint 1 health-checker deployed before you start here.
>
> If you need to start fresh, run Steps 1–8 of the Sprint 1 local guide,
> then come back here.

---

## Table of Contents

1. [Confirm Sprint 1 Is Running](#1-confirm-sprint-1-is-running)
2. [Update k8s_client.py — Richer Data](#2-update-k8s_clientpy--richer-data)
3. [Update monitor.py — New Metrics](#3-update-monitorpy--new-metrics)
4. [Update main.py — Health Summary Endpoint](#4-update-mainpy--health-summary-endpoint)
5. [Create the monitoring Manifests Folder](#5-create-the-monitoring-manifests-folder)
6. [Add PrometheusRule — Alert Thresholds](#6-add-prometheusrule--alert-thresholds)
7. [Add Grafana Dashboard ConfigMap](#7-add-grafana-dashboard-configmap)
8. [Update prometheus-values.yaml — Dashboard Sidecar](#8-update-prometheus-valuesyaml--dashboard-sidecar)
9. [Rebuild the Health-Checker Image Locally](#9-rebuild-the-health-checker-image-locally)
10. [Apply New Kubernetes Manifests](#10-apply-new-kubernetes-manifests)
11. [Verify Everything](#11-verify-everything)
12. [Teardown](#12-teardown)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. Confirm Sprint 1 Is Running

```bash
# minikube must be running
minikube status
# Expected: minikube: Running, cluster: Running, kubectl: Correctly Configured

# All Sprint 1 pods must be healthy
kubectl get pods -n default
# Expected: 10 pods all 1/1 Running (9 GratitudeApp services + health-checker)

kubectl get pods -n monitoring
# Expected: Prometheus, Grafana, Alertmanager all Running

# Health-checker must be reachable
kubectl port-forward -n default svc/health-checker-cluster-ip-service 8000:8000 &
sleep 2
curl http://localhost:8000/healthz
# Expected: {"status":"ok"}

# Kill the port-forward — we'll reopen it after the Sprint 2 redeploy
pkill -f "kubectl port-forward.*8000"
```

---

## 2. Update k8s_client.py — Richer Data

Open the file in your editor and replace its entire contents:

```bash
code k8s-health-checker/healthchecker-app/k8s_client.py
# or
nano k8s-health-checker/healthchecker-app/k8s_client.py
```

Paste the following and save:

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
            cond_map[c.type] = c.status

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

Verify the change:

```bash
grep "memory_pressure" k8s-health-checker/healthchecker-app/k8s_client.py
# Expected: a matching line — confirms the Sprint 2 field is present
```

---

## 3. Update monitor.py — New Metrics

Open and replace:

```bash
code k8s-health-checker/healthchecker-app/monitor.py
```

```python
# k8s-health-checker/healthchecker-app/monitor.py

import logging
import threading
import time

from prometheus_client import Gauge

from k8s_client import get_clients, list_deployments, list_nodes, list_pods

logger = logging.getLogger("monitor")

# ── Sprint 1 metrics (unchanged) ─────────────────────────────────────────────
NODE_READY = Gauge(
    "healthchecker_node_ready", "1 if node is Ready, 0 otherwise", ["node"])
POD_RESTARTS = Gauge(
    "healthchecker_pod_restarts_total", "Container restart count", ["namespace", "pod"])
POD_PHASE = Gauge(
    "healthchecker_pod_phase_running", "1 if pod phase is Running", ["namespace", "pod"])
DEPLOYMENT_AVAILABLE = Gauge(
    "healthchecker_deployment_available_replicas", "Available replicas", ["namespace", "deployment"])
DEPLOYMENT_DESIRED = Gauge(
    "healthchecker_deployment_desired_replicas", "Desired replicas", ["namespace", "deployment"])

# ── Sprint 2 metrics (new) ────────────────────────────────────────────────────
POD_READY = Gauge(
    "healthchecker_pod_ready", "1 if pod Ready condition is True", ["namespace", "pod"])
DEPLOYMENT_HEALTHY = Gauge(
    "healthchecker_deployment_healthy", "1 if available >= desired and desired > 0",
    ["namespace", "deployment"])
NODE_MEMORY_PRESSURE = Gauge(
    "healthchecker_node_memory_pressure", "1 if MemoryPressure is True", ["node"])
NODE_DISK_PRESSURE = Gauge(
    "healthchecker_node_disk_pressure", "1 if DiskPressure is True", ["node"])
NODE_PID_PRESSURE = Gauge(
    "healthchecker_node_pid_pressure", "1 if PIDPressure is True", ["node"])
POD_NOT_RUNNING = Gauge(
    "healthchecker_pod_not_running", "1 if pod phase is not Running", ["namespace", "pod"])

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
            1 if dep["healthy"] else 0)

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

## 4. Update main.py — Health Summary Endpoint

Open and replace:

```bash
code k8s-health-checker/healthchecker-app/main.py
```

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

        overall = (
            "critical" if any(i["severity"] == "critical" for i in issues)
            else "degraded" if issues
            else "healthy"
        )

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

## 5. Create the monitoring Manifests Folder

```bash
mkdir -p k8s-health-checker/deploy/monitoring
```

---

## 6. Add PrometheusRule — Alert Thresholds

```bash
cat > k8s-health-checker/deploy/monitoring/prometheus-rules.yaml << 'EOF'
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
              Node {{ $labels.node }} has been NotReady for more than 2 minutes.

        - alert: NodeMemoryPressure
          expr: healthchecker_node_memory_pressure == 1
          for: 2m
          labels:
            severity: warning
          annotations:
            summary: "Node {{ $labels.node }} is under memory pressure"
            description: >
              Node {{ $labels.node }} has reported MemoryPressure for over 2 minutes.

        - alert: NodeDiskPressure
          expr: healthchecker_node_disk_pressure == 1
          for: 2m
          labels:
            severity: warning
          annotations:
            summary: "Node {{ $labels.node }} is under disk pressure"
            description: >
              Node {{ $labels.node }} has reported DiskPressure for over 2 minutes.

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
              Pod {{ $labels.pod }} has not been Running for more than 5 minutes.

        - alert: PodHighRestartCount
          expr: healthchecker_pod_restarts_total{namespace="default"} > 5
          for: 1m
          labels:
            severity: warning
          annotations:
            summary: "Pod {{ $labels.pod }} has restarted {{ $value }} times"
            description: >
              Pod {{ $labels.pod }} has restarted more than 5 times. Likely CrashLoopBackOff.

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
              Deployment {{ $labels.deployment }} has fewer available replicas than desired.

        - alert: DeploymentZeroReplicas
          expr: healthchecker_deployment_available_replicas{namespace="default"} == 0
          for: 1m
          labels:
            severity: critical
          annotations:
            summary: "Deployment {{ $labels.deployment }} has ZERO replicas"
            description: >
              Deployment {{ $labels.deployment }} has 0 available replicas — service is down.
EOF
```

Verify:

```bash
cat k8s-health-checker/deploy/monitoring/prometheus-rules.yaml | grep "alert:"
# Expected: 7 alert names listed
```

---

## 7. Add Grafana Dashboard ConfigMap

```bash
cat > k8s-health-checker/deploy/monitoring/grafana-dashboard-cm.yaml << 'EOF'
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
            "steps": [{"color":"red","value":0},{"color":"green","value":1}] }}},
          "targets": [{"expr": "sum(healthchecker_node_ready)", "legendFormat": "Ready nodes"}]
        },
        {
          "id": 2, "type": "stat", "title": "Pods Running",
          "gridPos": { "x": 4, "y": 0, "w": 4, "h": 4 },
          "fieldConfig": { "defaults": { "thresholds": { "mode": "absolute",
            "steps": [{"color":"red","value":0},{"color":"yellow","value":5},{"color":"green","value":9}] }}},
          "targets": [{"expr": "sum(healthchecker_pod_phase_running{namespace='default'})", "legendFormat": "Running pods"}]
        },
        {
          "id": 3, "type": "stat", "title": "Deployments Healthy",
          "gridPos": { "x": 8, "y": 0, "w": 4, "h": 4 },
          "fieldConfig": { "defaults": { "thresholds": { "mode": "absolute",
            "steps": [{"color":"red","value":0},{"color":"green","value":9}] }}},
          "targets": [{"expr": "sum(healthchecker_deployment_healthy{namespace='default'})", "legendFormat": "Healthy"}]
        },
        {
          "id": 4, "type": "stat", "title": "Total Pod Restarts",
          "gridPos": { "x": 12, "y": 0, "w": 4, "h": 4 },
          "fieldConfig": { "defaults": { "thresholds": { "mode": "absolute",
            "steps": [{"color":"green","value":0},{"color":"yellow","value":5},{"color":"red","value":10}] }}},
          "targets": [{"expr": "sum(healthchecker_pod_restarts_total{namespace='default'})", "legendFormat": "Restarts"}]
        },
        {
          "id": 5, "type": "timeseries", "title": "Node Readiness Over Time",
          "gridPos": { "x": 0, "y": 4, "w": 12, "h": 8 },
          "targets": [{"expr": "healthchecker_node_ready", "legendFormat": "{{ node }}"}]
        },
        {
          "id": 6, "type": "timeseries", "title": "Pod Restart Rate",
          "gridPos": { "x": 12, "y": 4, "w": 12, "h": 8 },
          "targets": [{"expr": "healthchecker_pod_restarts_total{namespace='default'}", "legendFormat": "{{ pod }}"}]
        },
        {
          "id": 7, "type": "table", "title": "Deployment Replica Status",
          "gridPos": { "x": 0, "y": 12, "w": 12, "h": 8 },
          "targets": [
            {"expr": "healthchecker_deployment_available_replicas{namespace='default'}", "legendFormat": "available — {{ deployment }}", "instant": true},
            {"expr": "healthchecker_deployment_desired_replicas{namespace='default'}", "legendFormat": "desired — {{ deployment }}", "instant": true}
          ]
        },
        {
          "id": 8, "type": "timeseries", "title": "Node Pressure Conditions",
          "gridPos": { "x": 12, "y": 12, "w": 12, "h": 8 },
          "targets": [
            {"expr": "healthchecker_node_memory_pressure", "legendFormat": "MemoryPressure — {{ node }}"},
            {"expr": "healthchecker_node_disk_pressure",   "legendFormat": "DiskPressure — {{ node }}"},
            {"expr": "healthchecker_node_pid_pressure",    "legendFormat": "PIDPressure — {{ node }}"}
          ]
        }
      ]
    }
EOF
```

Verify both monitoring files exist:

```bash
ls k8s-health-checker/deploy/monitoring/
# Expected:
# grafana-dashboard-cm.yaml
# prometheus-rules.yaml
```

---

## 8. Update prometheus-values.yaml — Dashboard Sidecar

Open the file and find the existing `grafana:` block. Merge the `sidecar:`
section into it so the complete `grafana:` block looks like this:

```bash
code k8s-health-checker/deploy/prometheus/prometheus-values.yaml
```

The final `grafana:` block (merge, do not duplicate the key):

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

Confirm the sidecar key is present:

```bash
grep "sidecar" k8s-health-checker/deploy/prometheus/prometheus-values.yaml
# Expected: a line containing "sidecar:"
```

---

## 9. Rebuild the Health-Checker Image Locally

Point your shell at minikube's Docker daemon so the rebuilt image is
immediately visible to pods without any registry push.

### Step 9.1 — Switch to minikube's Docker daemon

```bash
eval $(minikube docker-env)

# Confirm you are talking to minikube's daemon
docker info | grep "Name:"
# Expected: Name: minikube
```

### Step 9.2 — Rebuild the image

```bash
docker build -t gratitude-health-checker:latest \
  k8s-health-checker/healthchecker-app/
```

### Step 9.3 — Confirm the image is in minikube

```bash
minikube image ls | grep gratitude-health-checker
# Expected: docker.io/library/gratitude-health-checker:latest
```

### Step 9.4 — Rolling restart the deployment

```bash
kubectl rollout restart deployment/health-checker-deployment -n default
```

### Step 9.5 — Wait for rollout to complete

```bash
kubectl rollout status deployment/health-checker-deployment -n default
# Expected: successfully rolled out

kubectl get pods -n default -l component=health-checker
# Expected: 1/1 Running with a fresh AGE (< 1 minute)
```

### Step 9.6 — Reset Docker to your host daemon

```bash
eval $(minikube docker-env --unset)
```

---

## 10. Apply New Kubernetes Manifests

### Step 10.1 — Apply the PrometheusRule

```bash
kubectl apply -f k8s-health-checker/deploy/monitoring/prometheus-rules.yaml
# Expected: prometheusrule.monitoring.coreos.com/gratitudeapp-health-rules created
```

### Step 10.2 — Apply the Grafana dashboard ConfigMap

```bash
kubectl apply -f k8s-health-checker/deploy/monitoring/grafana-dashboard-cm.yaml
# Expected: configmap/gratitudeapp-health-dashboard created
```

### Step 10.3 — Helm upgrade (adds the Grafana sidecar)

```bash
helm upgrade monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  -f k8s-health-checker/deploy/prometheus/prometheus-values.yaml
```

### Step 10.4 — Wait for monitoring pods to stabilise

```bash
kubectl wait --for=condition=Ready pods --all -n monitoring --timeout=300s
```

### Step 10.5 — Confirm all resources

```bash
# PrometheusRule
kubectl get prometheusrule -n monitoring
# Expected: gratitudeapp-health-rules

# Grafana dashboard ConfigMap
kubectl get configmap -n monitoring -l grafana_dashboard=1
# Expected: gratitudeapp-health-dashboard

# All monitoring pods still Running
kubectl get pods -n monitoring
```

---

## 11. Verify Everything

Open port-forwards in **separate terminals**, or background them as shown.

### Step 11.1 — Start port-forwards

```bash
# Terminal 1 — health-checker
kubectl port-forward -n default svc/health-checker-cluster-ip-service 8000:8000 &

# Terminal 2 — Grafana
kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80 &

# Terminal 3 — Prometheus
kubectl port-forward -n monitoring \
  svc/monitoring-kube-prometheus-prometheus 9090:9090 &

sleep 3   # let tunnels establish
```

### 11.2 New `/api/health-summary` endpoint

```bash
curl http://localhost:8000/api/health-summary | python3 -m json.tool
```

Expected output on a healthy cluster:

```json
{
    "status": "healthy",
    "issue_count": 0,
    "issues": [],
    "nodes_total": 1,
    "pods_total": 10,
    "deployments_total": 9
}
```

> `nodes_total: 1` is expected locally — minikube is a single-node cluster.

### 11.3 Verify all 11 metric families are exposed

```bash
curl -s http://localhost:8000/metrics | \
  grep "^healthchecker" | \
  awk -F'{' '{print $1}' | \
  sort -u
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

Spot-check individual new metrics:

```bash
# Pod ready — all should be 1.0
curl -s http://localhost:8000/metrics | grep "healthchecker_pod_ready{"

# Deployment healthy — all should be 1.0
curl -s http://localhost:8000/metrics | grep "healthchecker_deployment_healthy{"

# Node pressure — all should be 0.0 on a healthy minikube
curl -s http://localhost:8000/metrics | grep "healthchecker_node_memory_pressure"
```

### 11.4 Verify PrometheusRule is loaded in Prometheus

```bash
open http://localhost:9090/rules
# or
xdg-open http://localhost:9090/rules   # Linux
```

Look for three rule groups: `gratitudeapp.nodes`, `gratitudeapp.pods`,
`gratitudeapp.deployments` — all 7 rules should be listed with green state.

### 11.5 Trigger a test alert

Scale a deployment to 0 to force the `DeploymentZeroReplicas` alert to fire:

```bash
kubectl scale deployment moods-api-deployment --replicas=0 -n default

# Wait ~65 seconds (the rule fires after 1 minute)
sleep 65

# Open the Prometheus alerts page
open http://localhost:9090/alerts
# DeploymentUnavailable and DeploymentZeroReplicas should appear as Firing (red)
```

Restore and confirm the alert clears:

```bash
kubectl scale deployment moods-api-deployment --replicas=1 -n default
kubectl wait --for=condition=Ready pods -l component=moods-api \
  -n default --timeout=60s

# After ~1-2 minutes the alert should move from Firing → Pending → resolved
open http://localhost:9090/alerts
```

### 11.6 Verify the Grafana dashboard

```bash
open http://localhost:3000
# Username: admin   Password: changeme
```

Steps:
1. Go to **Dashboards → Browse**.
2. Find **"GratitudeApp — Cluster Health"** (auto-provisioned by the sidecar).
3. Confirm all 8 panels are populated:
   - Nodes Ready → `1` (single minikube node)
   - Pods Running → `10`
   - Deployments Healthy → `9`
   - Total Pod Restarts → a small number
   - Node Readiness Over Time → flat line at 1
   - Pod Restart Rate → low/zero lines per pod
   - Deployment Replica Status → table showing all 1/1
   - Node Pressure Conditions → all flat at 0

If the dashboard does not appear within 60 seconds, check the sidecar:

```bash
kubectl logs -n monitoring \
  -l app.kubernetes.io/name=grafana \
  -c grafana-sc-dashboard | tail -20
# Look for: "Configmap added" or "Starting dashboard provisioner"
```

### 11.7 minikube node pressure check

On minikube, node pressure conditions reflect real host resource constraints.
If your machine is running low on memory, `healthchecker_node_memory_pressure`
may actually show `1.0` — this is expected and the alert will fire after 2 min.

```bash
# Check current node conditions
kubectl describe node minikube | grep -A 10 "Conditions:"
```

---

## 12. Teardown

### Stop port-forwards

```bash
pkill -f "kubectl port-forward"
```

### Remove Sprint 2 resources only (keep Sprint 1 running)

```bash
helm upgrade monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  -f k8s-health-checker/deploy/prometheus/prometheus-values.yaml \
  --set grafana.sidecar.dashboards.enabled=false

kubectl delete -f k8s-health-checker/deploy/monitoring/prometheus-rules.yaml
kubectl delete -f k8s-health-checker/deploy/monitoring/grafana-dashboard-cm.yaml
```

### Full teardown (all sprints)

```bash
helm uninstall monitoring -n monitoring

kubectl delete -f k8s-local/healthchecker-deployment-local.yaml
kubectl delete -f k8s-health-checker/deploy/healthchecker/rbac.yaml

K8S="k8s-health-checker/gratitude-k8s"
kubectl delete -f $K8S/ingress-service.yml
kubectl delete -f $K8S/client-service.yml
kubectl delete -f $K8S/client-cluster-ip-service.yml
kubectl delete -f $K8S/client-deployment.yml
kubectl delete -f $K8S/server-cluster-ip-service.yml
kubectl delete -f $K8S/server-deployment.yml
kubectl delete -f $K8S/files-service-cluster-ip-service.yml
kubectl delete -f $K8S/files-service-deployment.yml
kubectl delete -f $K8S/stats-service-cluster-ip-service.yml
kubectl delete -f $K8S/stats-service-deployment.yml
kubectl delete -f $K8S/stats-api-cluster-ip-service.yml
kubectl delete -f $K8S/stats-api-deployment.yml
kubectl delete -f $K8S/moods-service-cluster-ip-service.yml
kubectl delete -f $K8S/moods-service-deployment.yml
kubectl delete -f $K8S/moods-api-cluster-ip-service.yml
kubectl delete -f $K8S/moods-api-deployment.yml
kubectl delete -f $K8S/entries-cluster-ip-service.yml
kubectl delete -f $K8S/entries-deployment.yml
kubectl delete -f $K8S/api-gateway-cluster-ip-service.yml
kubectl delete -f $K8S/api-gateway-deployment.yml
kubectl delete -f $K8S/postgres-cluster-ip-service.yml
kubectl delete -f $K8S/postgres-deployment.yml
kubectl delete -f $K8S/database-persistent-volume-claim.yml
kubectl delete -f $K8S/openai-api-secret.yml
kubectl delete -f $K8S/postgres-init-config.yml
kubectl delete -f $K8S/database-secret.yml
kubectl delete -f k8s-local/storageclass-local.yaml

minikube stop     # pause cluster
# or
minikube delete   # wipe everything
```

---

## 13. Troubleshooting

### PrometheusRule not appearing in Prometheus `/rules`

The `kube-prometheus-stack` chart picks up `PrometheusRule` resources with
the label `release: monitoring`. Confirm the label is present:

```bash
kubectl get prometheusrule -n monitoring -o yaml | grep "release:"
# Expected: release: monitoring
```

If missing, the rule was applied without the label — delete and re-apply:

```bash
kubectl delete prometheusrule gratitudeapp-health-rules -n monitoring
kubectl apply -f k8s-health-checker/deploy/monitoring/prometheus-rules.yaml
```

Allow 30–60 seconds for Prometheus to reload its config.

### Grafana dashboard not appearing after 60 seconds

```bash
# Check the sidecar is running
kubectl get pods -n monitoring | grep grafana

# Check sidecar logs for errors
kubectl logs -n monitoring \
  -l app.kubernetes.io/name=grafana \
  -c grafana-sc-dashboard | tail -30

# Confirm the ConfigMap has the right label
kubectl get configmap gratitudeapp-health-dashboard -n monitoring \
  -o jsonpath='{.metadata.labels}'
# Expected: {"grafana_dashboard":"1"}
```

If the Helm upgrade did not enable the sidecar, force it:

```bash
helm upgrade monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  -f k8s-health-checker/deploy/prometheus/prometheus-values.yaml \
  --set grafana.sidecar.dashboards.enabled=true \
  --set grafana.sidecar.dashboards.label=grafana_dashboard \
  --set grafana.sidecar.dashboards.searchNamespace=ALL
```

### `ErrImageNeverPull` after rollout restart

The rebuilt image was not loaded into minikube's daemon:

```bash
eval $(minikube docker-env)
docker images | grep gratitude-health-checker
# If empty — rebuild:
docker build -t gratitude-health-checker:latest \
  k8s-health-checker/healthchecker-app/
eval $(minikube docker-env --unset)

kubectl rollout restart deployment/health-checker-deployment -n default
```

### `healthchecker_node_memory_pressure` shows `1.0`

This is genuine — your host machine (running minikube) is under memory
pressure. The alert will fire after 2 minutes. Free up RAM on your host
or give minikube more memory:

```bash
minikube stop
minikube delete
minikube start --cpus=4 --memory=8192 --driver=docker
# Then re-run the full deployment from Step 6
```

---

## Sprint 2 Local Deliverables Checklist

- [ ] `grep "memory_pressure" k8s_client.py` returns a match
- [ ] `grep "healthchecker_pod_ready" monitor.py` returns a match
- [ ] `grep "health-summary" main.py` returns a match
- [ ] Image rebuilt inside minikube daemon (`minikube image ls | grep gratitude`)
- [ ] `kubectl rollout status` shows `successfully rolled out`
- [ ] `curl /api/health-summary` returns `{"status":"healthy",...}`
- [ ] All 11 metric families present at `/metrics`
- [ ] `kubectl get prometheusrule -n monitoring` shows `gratitudeapp-health-rules`
- [ ] Prometheus `/rules` page lists all 7 alert rules
- [ ] Scaling to 0 replicas fires `DeploymentZeroReplicas` alert within ~65 seconds
- [ ] `kubectl get configmap -n monitoring -l grafana_dashboard=1` returns the dashboard CM
- [ ] Grafana **"GratitudeApp — Cluster Health"** dashboard shows all 8 panels
