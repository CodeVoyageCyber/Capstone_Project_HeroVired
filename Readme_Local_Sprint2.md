# Sprint 2 — Health Monitoring Module: Step-by-Step Guide (Local / Minikube)

**Goal:** Extend the health-checker with per-pod readiness/condition detail and a
per-deployment "all replicas available" gauge for each GratitudeApp service, provision
a Grafana dashboard that visualises node/pod health and service availability, and
define initial Alertmanager rules for critical thresholds — all running locally with
Minikube.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [What Changed in Sprint 2](#2-what-changed-in-sprint-2)
3. [Extend `k8s_client.py` — Pod Conditions & Readiness](#3-extend-k8s_clientpy--pod-conditions--readiness)
4. [Extend `monitor.py` — New Prometheus Gauges](#4-extend-monitorpy--new-prometheus-gauges)
5. [Build the Docker Image (Minikube)](#5-build-the-docker-image-minikube)
6. [Update & Redeploy the Health-Checker](#6-update--redeploy-the-health-checker)
7. [Add the Grafana Dashboard](#7-add-the-grafana-dashboard)
8. [Add Alertmanager Alert Rules](#8-add-alertmanager-alert-rules)
9. [Verify Everything](#9-verify-everything)
10. [Testing Alerts](#10-testing-alerts)
11. [Sprint 2 Deliverables Checklist](#11-sprint-2-deliverables-checklist)

---

## 1. Prerequisites

The following must already be running from Sprint 1 local setup:

```bash
# Minikube running
minikube status
# Expected: host: Running, kubelet: Running, apiserver: Running

# All GratitudeApp pods healthy
kubectl get pods -n default
# Expected: all services 1/1 Running

# kube-prometheus-stack installed in the monitoring namespace
helm list -n monitoring
# Expected: monitoring  monitoring  1  deployed  kube-prometheus-stack-x.x.x

# Minikube IP
minikube ip
# Expected: 192.168.49.2
```

No new tools are required for Sprint 2.

---

## 2. What Changed in Sprint 2

### New Prometheus metrics exposed by `health-checker`

| Metric | Labels | Description |
|--------|--------|-------------|
| `healthchecker_pod_ready` | `namespace`, `pod` | `1` if pod `Ready` condition is `True`, `0` otherwise |
| `healthchecker_deployment_all_replicas_available` | `namespace`, `deployment` | `1` if `available == desired`, `0` if degraded |

### Existing metrics (unchanged from Sprint 1)

| Metric | Labels | Description |
|--------|--------|-------------|
| `healthchecker_node_ready` | `node` | `1` if node is Ready |
| `healthchecker_pod_restarts_total` | `namespace`, `pod` | Container restart count |
| `healthchecker_pod_phase_running` | `namespace`, `pod` | `1` if phase is Running |
| `healthchecker_deployment_available_replicas` | `namespace`, `deployment` | Available replica count |
| `healthchecker_deployment_desired_replicas` | `namespace`, `deployment` | Desired replica count |

### New Kubernetes resources

| Resource | Kind | Namespace | Purpose |
|----------|------|-----------|---------|
| `node-pod-health-dashboard` | ConfigMap | `monitoring` | Grafana dashboard (auto-loaded via sidecar) |
| `gratitudeapp-health-alerts` | PrometheusRule | `monitoring` | 4 alert rules for node/pod/deployment health |

### New API response fields (`/api/pods`)

Each pod object now includes:
- `ready` — boolean (`true`/`false`) derived from the Kubernetes `Ready` condition
- `conditions` — map of all pod conditions with `status`, `reason`, and `message`

---

## 3. Extend `k8s_client.py` — Pod Conditions & Readiness

**File:** [`k8s-health-checker/healthchecker-app/k8s_client.py`](k8s-health-checker/healthchecker-app/k8s_client.py)

The `list_pods()` function was extended to collect per-pod readiness and condition detail:

```python
def list_pods(core: client.CoreV1Api, namespace: str = "default"):
    """Return pod name, phase, restart count, readiness, conditions and node."""
    pods = core.list_namespaced_pod(namespace)
    result = []
    for pod in pods.items:
        restarts = sum(
            (cs.restart_count or 0) for cs in (pod.status.container_statuses or [])
        )
        # Collect all conditions as {type: {status, reason, message}} dicts
        conditions = {}
        if pod.status.conditions:
            for c in pod.status.conditions:
                conditions[c.type] = {
                    "status": c.status,
                    "reason": c.reason or "",
                    "message": c.message or "",
                }
        # Pod is "ready" when the Ready condition is True
        ready = conditions.get("Ready", {}).get("status", "False") == "True"
        result.append(
            {
                "name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "phase": pod.status.phase,
                "ready": ready,
                "restarts": restarts,
                "node": pod.spec.node_name,
                "conditions": conditions,
            }
        )
    return result
```

---

## 4. Extend `monitor.py` — New Prometheus Gauges

**File:** [`k8s-health-checker/healthchecker-app/monitor.py`](k8s-health-checker/healthchecker-app/monitor.py)

Two new Prometheus gauges are registered and populated on every poll cycle:

```python
POD_READY = Gauge(
    "healthchecker_pod_ready",
    "1 if pod Ready condition is True, 0 otherwise",
    ["namespace", "pod"],
)

DEPLOYMENT_ALL_AVAILABLE = Gauge(
    "healthchecker_deployment_all_replicas_available",
    "1 if available replicas == desired replicas, 0 otherwise",
    ["namespace", "deployment"],
)
```

In `collect_once()`, these are updated alongside the existing metrics:

```python
# Per pod — readiness
POD_READY.labels(namespace=pod["namespace"], pod=pod["name"]).set(
    1 if pod.get("ready") else 0
)

# Per deployment — all replicas available check
all_ok = 1 if (desired > 0 and available >= desired) else 0
DEPLOYMENT_ALL_AVAILABLE.labels(
    namespace=dep["namespace"], deployment=dep["name"]
).set(all_ok)
```

---

## 5. Build the Docker Image (Minikube)

Because Minikube runs its own container runtime, use `minikube image build` to build
the image directly inside Minikube — no Docker registry is needed.

```bash
cd k8s-health-checker/healthchecker-app

minikube image build -t health-checker:sprint2 .
```

Expected output (abbreviated):

```
#8 DONE 28.0s
#9 [5/6] COPY . .
#10 [6/6] RUN useradd -m appuser
#11 exporting to image
#11 naming to docker.io/library/health-checker:sprint2 done
#11 DONE 3.8s
```

Verify the image is available inside Minikube:

```bash
minikube image ls | grep health-checker
# Expected: docker.io/library/health-checker:sprint2
```

> **Why not `docker build` with `eval $(minikube docker-env)`?**
> Docker Desktop on macOS sets `docker-container` as the default buildx driver,
> which tries to spin up a `moby/buildkit` container on Minikube's daemon and
> fails with `404`. `minikube image build` bypasses buildx entirely.

---

## 6. Update & Redeploy the Health-Checker

**File:** [`k8s-health-checker/deploy/healthchecker/deployment.yaml`](k8s-health-checker/deploy/healthchecker/deployment.yaml)

The image reference was updated from the ECR placeholder to the local tag:

```yaml
# Sprint 1 (ECR, for AWS)
image: <YOUR_ECR_OR_DOCKERHUB_IMAGE>:latest

# Sprint 2 (local Minikube)
image: health-checker:sprint2
imagePullPolicy: Never          # ← prevents Kubernetes from trying to pull remotely
```

Apply the updated manifest:

```bash
kubectl apply -f k8s-health-checker/deploy/healthchecker/deployment.yaml
```

Expected output:
```
deployment.apps/health-checker-deployment configured
service/health-checker-cluster-ip-service unchanged
```

Watch the rollout:

```bash
kubectl rollout status deployment/health-checker-deployment -n default --timeout=90s
```

Expected output:
```
Waiting for deployment "health-checker-deployment" rollout to finish: 1 old replicas are pending termination...
Waiting for deployment "health-checker-deployment" rollout to finish: 1 old replicas are pending termination...
deployment "health-checker-deployment" successfully rolled out
```

Confirm the new pod is running:

```bash
kubectl get pod -n default -l component=health-checker -o wide
```

Expected output:
```
NAME                                        READY   STATUS    RESTARTS   AGE   IP             NODE       NOMINATED NODE   READINESS GATES
health-checker-deployment-d7474d6b6-mv775   1/1     Running   0          33s   10.244.0.22    minikube   <none>           <none>
```

---

## 7. Add the Grafana Dashboard

**File:** [`k8s-health-checker/deploy/grafana/node-pod-health-dashboard.yaml`](k8s-health-checker/deploy/grafana/node-pod-health-dashboard.yaml)

The dashboard is provisioned as a Kubernetes ConfigMap with the label
`grafana_dashboard: "1"`. The `grafana-sc-dashboard` sidecar that ships with
`kube-prometheus-stack` watches for this label across all namespaces and
hot-loads matching ConfigMaps into Grafana within ~30 seconds — no Grafana
restart is required.

Apply the ConfigMap:

```bash
kubectl apply -f k8s-health-checker/deploy/grafana/node-pod-health-dashboard.yaml
```

Expected output:
```
configmap/node-pod-health-dashboard created
```

Verify the sidecar picked it up:

```bash
kubectl logs -n monitoring \
  $(kubectl get pod -n monitoring -l app.kubernetes.io/name=grafana -o name | head -1) \
  -c grafana-sc-dashboard | tail -10
```

Access Grafana:

```bash
kubectl port-forward svc/monitoring-grafana 3000:80 -n monitoring
# Open: http://localhost:3000
# Username: admin  |  Password: changeme
```

Navigate to **Dashboards → GratitudeApp — Node & Pod Health**.

The dashboard includes 5 panels:

| Panel | Type | Query |
|-------|------|-------|
| Node Ready Status | Stat | `healthchecker_node_ready` |
| Pod Ready — GratitudeApp | Table | `healthchecker_pod_ready{namespace="default"}` |
| Deployment — All Replicas Available | Stat | `healthchecker_deployment_all_replicas_available{namespace="default"}` |
| Available vs Desired Replicas | Time series | `healthchecker_deployment_available/desired_replicas` |
| Pod Restart Count | Time series | `healthchecker_pod_restarts_total{namespace="default"}` |

### Screenshot — Grafana Dashboard

> "GratitudeApp — Node & Pod Health" Grafana dashboard here.
<img width="3340" height="800" alt="image" src="https://github.com/user-attachments/assets/842a633d-8d13-454d-9c58-760f2b2297e1" />

<img width="3404" height="1930" alt="image" src="https://github.com/user-attachments/assets/db37207a-97ab-420a-8c75-4720f4ee532f" />

---

## 8. Add Alertmanager Alert Rules

**File:** [`k8s-health-checker/deploy/alerts/gratitudeapp-alerts.yaml`](k8s-health-checker/deploy/alerts/gratitudeapp-alerts.yaml)

Alert rules are defined as a `PrometheusRule` custom resource. The label
`release: monitoring` (matching the Helm release name) tells the Prometheus
Operator to load this rule file.

Apply the rules:

```bash
kubectl apply -f k8s-health-checker/deploy/alerts/gratitudeapp-alerts.yaml
```

Expected output:
```
prometheusrule.monitoring.coreos.com/gratitudeapp-health-alerts created
```

Verify the PrometheusRule was created:

```bash
kubectl get prometheusrule -n monitoring gratitudeapp-health-alerts
```

Expected output:
```
NAME                         AGE
gratitudeapp-health-alerts   30s
```

### Alert definitions

| Alert | Expr | For | Severity | Description |
|-------|------|-----|----------|-------------|
| `NodeNotReady` | `healthchecker_node_ready == 0` | 2m | critical | Node has been NotReady for > 2 min |
| `GratitudeAppDeploymentDegraded` | `healthchecker_deployment_all_replicas_available{deployment=~"..."} == 0` | 1m | warning | Any GratitudeApp deployment with available < desired for > 1 min |
| `PodHighRestartCount` | `healthchecker_pod_restarts_total{namespace="default"} > 5` | 0m | warning | Pod has accumulated > 5 restarts |
| `PodNotReady` | `healthchecker_pod_ready == 0 and healthchecker_pod_phase_running == 1` | 2m | warning | Pod is Running but Ready condition is False for > 2 min |

Check alerts in the Prometheus UI:

```bash
kubectl port-forward svc/monitoring-kube-prometheus-prometheus 9090:9090 -n monitoring
# Open: http://localhost:9090/alerts
```

### Screenshot — Prometheus Alert Rules

<img width="3390" height="1406" alt="image" src="https://github.com/user-attachments/assets/275f063a-10fa-43d1-b4c2-9382e72e1d83" />

---

## 9. Verify Everything

### 9.1 Health-checker pod is running the new image

```bash
kubectl get pod -n default -l component=health-checker -o wide
# Expected: 1/1 Running, AGE < 5m (fresh rollout)
```

### 9.2 New Prometheus metrics are being exported

```bash
kubectl port-forward svc/health-checker-cluster-ip-service 8000:8000 -n default &

# Liveness check
curl http://localhost:8000/healthz
# Expected: {"status":"ok"}

# New Sprint 2 metrics
curl -s http://localhost:8000/metrics | grep healthchecker_pod_ready
# Expected: lines like:
# healthchecker_pod_ready{namespace="default",pod="api-gateway-deployment-xxx"} 1.0
# healthchecker_pod_ready{namespace="default",pod="client-deployment-xxx"} 1.0
# ...

curl -s http://localhost:8000/metrics | grep healthchecker_deployment_all_replicas
# Expected: lines like:
# healthchecker_deployment_all_replicas_available{deployment="api-gateway-deployment",namespace="default"} 1.0
# healthchecker_deployment_all_replicas_available{deployment="postgres-deployment",namespace="default"} 1.0
# ...

kill %1
```

### Screenshot — `/metrics` endpoint output
<img width="1860" height="1878" alt="image" src="https://github.com/user-attachments/assets/c093e773-5608-40db-a599-d3ac97dec364" />


### 9.3 `/api/pods` now returns `ready` and `conditions` fields

```bash
kubectl port-forward svc/health-checker-cluster-ip-service 8000:8000 -n default &

curl -s http://localhost:8000/api/pods | python3 -m json.tool | head -40
# Expected: each pod now has "ready": true/false and "conditions": {...}
```

Example pod object:
```json
{
    "name": "api-gateway-deployment-76d745f8b4-8w8vs",
    "namespace": "default",
    "phase": "Running",
    "ready": true,
    "restarts": 1,
    "node": "minikube",
    "conditions": {
        "PodReadyToStartContainers": {"status": "True", "reason": "", "message": ""},
        "Initialized":              {"status": "True", "reason": "", "message": ""},
        "Ready":                    {"status": "True", "reason": "", "message": ""},
        "ContainersReady":          {"status": "True", "reason": "", "message": ""},
        "PodScheduled":             {"status": "True", "reason": "", "message": ""}
    }
}
```

### 9.4 `/api/summary` includes all three health dimensions

```bash
curl -s http://localhost:8000/api/summary | python3 -m json.tool
# Expected: {"nodes": [...], "pods": [...], "deployments": [...]}
# All deployments should show "available" == "desired"
```

### 9.5 Prometheus is scraping the health-checker

```bash
kubectl port-forward svc/monitoring-kube-prometheus-prometheus 9090:9090 -n monitoring &
# Open: http://localhost:9090/targets
# Look for: health-checker job → State: UP
```

### Screenshot — Prometheus Targets

<img width="3382" height="896" alt="image" src="https://github.com/user-attachments/assets/bb17af20-da3e-4b8b-9587-2eaf4b2d94e9" />


### 9.6 Grafana dashboard is visible

```bash
kubectl port-forward svc/monitoring-grafana 3000:80 -n monitoring &
# Open: http://localhost:3000
# Navigate: Dashboards → GratitudeApp — Node & Pod Health
```

---

## 10. Testing Alerts

You can trigger the `GratitudeAppDeploymentDegraded` alert manually to confirm
the alerting pipeline is working end-to-end.

### 10.1 Trigger the alert — scale a deployment to 0

```bash
kubectl scale deployment client-deployment --replicas=0 -n default
```

Wait ~90 seconds, then check the Prometheus alerts page:

```bash
# Open: http://localhost:9090/alerts
# Look for: GratitudeAppDeploymentDegraded in PENDING state (after 30s)
# then FIRING state (after 1 minute)
```

Expected alert state progression:
```
Inactive → Pending (after ~30s) → Firing (after 1m)
```

### Screenshot — Alert FIRING

<img width="2086" height="120" alt="image" src="https://github.com/user-attachments/assets/a2927a07-80e7-4826-a3ea-b7c298859160" />
<img width="3420" height="1376" alt="image" src="https://github.com/user-attachments/assets/30c5fedf-c96d-4741-bc13-3051791d4fd0" />
<img width="3386" height="1382" alt="image" src="https://github.com/user-attachments/assets/2a77434b-a75f-4a0c-96dc-82549fa25dc2" />


### 10.2 Restore the deployment

```bash
kubectl scale deployment client-deployment --replicas=1 -n default
kubectl rollout status deployment/client-deployment -n default
# Once restored, the alert will return to Inactive state
```

---

## 11. Sprint 2 Deliverables Checklist

### Code changes
- [x] `k8s_client.py` — `list_pods()` returns `ready` (bool) and `conditions` (dict) per pod
- [x] `monitor.py` — `POD_READY` Prometheus gauge added and populated in `collect_once()`
- [x] `monitor.py` — `DEPLOYMENT_ALL_AVAILABLE` gauge added (`1` if available ≥ desired)
- [x] `monitor.py` — `GRATITUDEAPP_SERVICES` list documents all 10 GratitudeApp deployments

### Infrastructure
- [x] Docker image `health-checker:sprint2` built inside Minikube with `minikube image build`
- [x] `deploy/healthchecker/deployment.yaml` updated with `sprint2` image tag and `imagePullPolicy: Never`
- [x] `deploy/grafana/node-pod-health-dashboard.yaml` created (ConfigMap, label `grafana_dashboard: "1"`)
- [x] `deploy/alerts/gratitudeapp-alerts.yaml` created (PrometheusRule, label `release: monitoring`)

### Verification
- [ ] `kubectl rollout status deployment/health-checker-deployment` → `successfully rolled out`
- [ ] `curl http://localhost:8000/metrics | grep healthchecker_pod_ready` → returns per-pod gauges
- [ ] `curl http://localhost:8000/metrics | grep healthchecker_deployment_all_replicas` → all `1.0`
- [ ] `curl http://localhost:8000/api/pods` → each pod object has `ready` and `conditions` fields
- [ ] `kubectl get prometheusrule -n monitoring gratitudeapp-health-alerts` → exists
- [ ] `kubectl get configmap -n monitoring node-pod-health-dashboard` → exists
- [ ] Grafana dashboard **"GratitudeApp — Node & Pod Health"** visible at `http://localhost:3000`
- [ ] Prometheus targets page shows `health-checker` job as **UP**
- [ ] All 4 alert rules (`NodeNotReady`, `GratitudeAppDeploymentDegraded`, `PodHighRestartCount`, `PodNotReady`) visible at `http://localhost:9090/alerts`
- [ ] Scaling `client-deployment` to 0 triggers `GratitudeAppDeploymentDegraded` alert to **FIRING**
- [ ] Restoring `client-deployment` to 1 replica resolves the alert to **Inactive**
