# Sprint 6 — Web Dashboard and Project Documentation: Step-by-Step Guide

**Goal:** Deliver a comprehensive Grafana observability dashboard for GratitudeApp's services, wire Prometheus metrics and alert/action history into the dashboard, produce full user documentation, and perform final end-to-end testing and teardown.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [What's New in Sprint 6](#2-whats-new-in-sprint-6)
3. [Dashboard Architecture](#3-dashboard-architecture)
4. [Step 1: Apply the Sprint 6 Full Observability Dashboard](#4-step-1-apply-the-sprint-6-full-observability-dashboard)
5. [Step 2: Open and Explore the Grafana Dashboard](#5-step-2-open-and-explore-the-grafana-dashboard)
6. [Step 3: Review User Documentation](#6-step-3-review-user-documentation)
7. [Step 4: Final End-to-End Test](#7-step-4-final-end-to-end-test)
   - 7.1 [Verify Full GratitudeApp Stack](#71-verify-full-gratitudeapp-stack)
   - 7.2 [Trigger & Observe Self-Healing in Grafana](#72-trigger--observe-self-healing-in-grafana)
   - 7.3 [Trigger & Observe HPA Scale-Out in Grafana](#73-trigger--observe-hpa-scale-out-in-grafana)
   - 7.4 [Trigger & Observe Prometheus Alert in Grafana](#74-trigger--observe-prometheus-alert-in-grafana)
   - 7.5 [Verify Slack Notification Delivery](#75-verify-slack-notification-delivery)
8. [Step-by-Step Screenshot Guide](#8-step-by-step-screenshot-guide)
9. [Step 5: Teardown](#9-step-5-teardown)
10. [Sprint 6 Deliverables Checklist](#10-sprint-6-deliverables-checklist)

---

## 1. Prerequisites

Before beginning Sprint 6, confirm the full stack from Sprints 1–5 is healthy:

```bash
# 1. Minikube running
minikube status
# Expected: host: Running, kubelet: Running, apiserver: Running

# 2. GratitudeApp pods healthy
kubectl get pods -n default
# Expected: ~10 pods Running (including health-checker-deployment-xxx)

# 3. Monitoring stack active
kubectl get pods -n monitoring
# Expected: Prometheus, Grafana, Alertmanager pods Running

# 4. Health-checker running (deployed in default namespace)
kubectl get pods -n default -l component=health-checker
# Expected: health-checker-deployment-xxx   1/1   Running

# 5. Health-checker API responding
kubectl port-forward svc/health-checker-cluster-ip-service -n default 8000:8000 &
sleep 2
curl -s http://localhost:8000/healthz
# Expected: {"status":"ok"}
```

---

## 2. What's New in Sprint 6

| Component | Description | File |
|-----------|-------------|------|
| **Full Observability Dashboard** | 12-panel Grafana dashboard: node health, deployment status, HPA scaling, pod phase pie chart, cluster balance trend, active alerts list | [`deploy/grafana/sprint6-full-dashboard.yaml`](k8s-health-checker/deploy/grafana/sprint6-full-dashboard.yaml) |
| **User Guide** | Complete setup, configuration, API reference, Prometheus metrics reference, and troubleshooting guide | [`docs/user-guide.md`](docs/user-guide.md) |
| **Teardown Script** | Automated removal of all project resources with colored output and `--delete-cluster` option | [`scripts/99-teardown.sh`](scripts/99-teardown.sh) |

---

## 3. Dashboard Architecture

The Sprint 6 dashboard (`gratitude-s6-v1`) surfaces all metrics produced across the 6 sprints in a single unified view:

```
Sprint 6 Full Observability Dashboard (grafana-sc-dashboard auto-provisioned)
│
├── Row 1: Live Status (instant queries — no stale data)
│   ├── Panel 1:  Node Ready Status            (healthchecker_node_ready)
│   ├── Panel 2:  Cluster Balance Ratio        (healthchecker_cluster_balance_ratio)
│   └── Panel 3:  Pods per Node                (healthchecker_node_pod_count)
│
├── Row 2: Deployment Health
│   └── Panel 4:  Deployment Health — All Replicas Available
│                 (healthchecker_deployment_all_replicas_available)
│
├── Row 3: Historical Trends (time-series)
│   ├── Panel 5:  Available vs Desired Replicas
│   └── Panel 6:  Pod Restart Count (rising = crash-looping)
│
├── Row 4: Pod Details
│   ├── Panel 7:  Pod Readiness Table (per-pod snapshot)
│   └── Panel 8:  Pod Phase Distribution (pie chart)
│
├── Row 5: Autoscaling & Resources
│   ├── Panel 9:  HPA — Current/Min/Max Replicas (kube-state-metrics)
│   └── Panel 10: CPU Allocatable per Node
│
└── Row 6: Alerts & Balance Trend
    ├── Panel 11: Active Prometheus Alerts (alertlist panel — live)
    └── Panel 12: Cluster Balance Ratio — Historical Trend
```

---

## 4. Step 1: Apply the Sprint 6 Full Observability Dashboard

```bash
# Apply the new dashboard ConfigMap
kubectl apply -f k8s-health-checker/deploy/grafana/sprint6-full-dashboard.yaml

# Verify the ConfigMap was created
kubectl get configmap sprint6-full-dashboard -n monitoring
# Expected: NAME                     DATA   AGE
#           sprint6-full-dashboard   1      <time>

# The Grafana sidecar (grafana-sc-dashboard) auto-detects the label
# "grafana_dashboard: 1" and hot-reloads the dashboard without a restart.
# Wait ~30 seconds for the sidecar to pick it up.

# Verify health-checker is serving metrics (it runs in default namespace)
kubectl get pods -n default -l component=health-checker
kubectl port-forward svc/health-checker-cluster-ip-service -n default 8000:8000 &
curl -s http://localhost:8000/metrics | grep healthchecker_ | head -5
```

**Verify the existing Sprint 2 dashboard is still present:**

```bash
kubectl get configmap -n monitoring | grep dashboard
# Expected:
# node-pod-health-dashboard   1   <time>    ← Sprint 2
# sprint6-full-dashboard      1   <time>    ← Sprint 6 (new)
```

---

## 5. Step 2: Open and Explore the Grafana Dashboard

### 5.1 Port-Forward Grafana

```bash
# Kill any existing port-forward on 3000 first
pkill -f "port-forward.*3000" 2>/dev/null || true

kubectl port-forward svc/monitoring-grafana -n monitoring 3000:80
```

Open **http://localhost:3000** in your browser.

```
Username: admin
Password: changeme
```

### 5.2 Navigate to the Dashboard

1. Click **Dashboards** (grid icon) in the left sidebar
2. Select **Browse**
3. Look for **"GratitudeApp — Full Observability Dashboard (Sprint 6)"**
4. Click to open

> **Note:** If the dashboard doesn't appear after 30 seconds, check the Grafana sidecar:
> ```bash
> kubectl logs -n monitoring \
>   $(kubectl get pod -n monitoring -l app.kubernetes.io/name=grafana -o jsonpath='{.items[0].metadata.name}') \
>   -c grafana-sc-dashboard --tail=20
> ```
### Screenshot — `http://localhost:3000`
<img width="3412" height="1584" alt="image" src="https://github.com/user-attachments/assets/334b13aa-7fb3-4505-9c86-9325eb2d0805" />
<img width="2758" height="1426" alt="image" src="https://github.com/user-attachments/assets/c5cf2182-266c-4df2-9a3d-5c3f7726200d" />
<img width="3246" height="624" alt="image" src="https://github.com/user-attachments/assets/c76fe0b5-63f2-495d-9570-775850fadde0" />


### 5.3 Explore Each Panel

| Panel | What to Look For |
|-------|-----------------|
| **Node Ready Status** | All nodes should show green "Ready" |
| **Cluster Balance Ratio** | Should be 1.0 on single-node Minikube |
| **Pods per Node** | All pods scheduled to the single Minikube node |
| **Deployment Health** | All 10 deployments should show green "OK" |
| **Available vs Desired Replicas** | Lines should overlap (available = desired) |
| **Pod Restart Count** | Should be flat/zero for healthy pods |
| **Pod Readiness Table** | All pods showing "Ready" |
| **Pod Phase Distribution** | All pods in the "Running" slice |
| **HPA Replicas** | Current = 1 (at rest, no load) |
| **Active Alerts** | Should show "No alerts" when healthy |

### 5.4 Adjust the Time Range

- Default: **Last 1 hour** (shows historical data from the current session)
- Change to **Last 6 hours** to see trends from earlier testing
- Use the refresh button (top-right) to get live updates every 30 seconds

---

## 6. Step 3: Review User Documentation

The full project user guide is at [`docs/user-guide.md`](docs/user-guide.md) and covers:

| Section | Contents |
|---------|----------|
| **Overview** | System capabilities summary |
| **Architecture** | ASCII diagram of all components |
| **Prerequisites** | Tool versions and Minikube resource requirements |
| **Setup & Installation** | End-to-end deploy steps (all 5 phases) |
| **Configuration Reference** | All env variables, healing thresholds, Slack config, Alertmanager routing, HPA settings |
| **Usage Guide** | All API endpoints, Grafana dashboard guide, manual healing, test alerts, chaos experiments |
| **Prometheus Metrics Reference** | All 10 metrics with labels, types, and example PromQL |
| **Troubleshooting Guide** | 6 common failure modes with diagnostic commands |
| **Teardown** | Full teardown steps |

```bash
# View the guide in terminal
cat docs/user-guide.md | less

# Or open in your editor
code docs/user-guide.md
```

---

## 7. Step 4: Final End-to-End Test

### 7.1 Verify Full GratitudeApp Stack

```bash
# Confirm all expected services are running
kubectl get pods -n default

# Expected output — ~11 Running pods (10 GratitudeApp + health-checker):
# NAME                                         READY   STATUS    RESTARTS
# api-gateway-deployment-xxx                   1/1     Running   0
# client-deployment-xxx                        1/1     Running   0
# entries-deployment-xxx                       1/1     Running   0
# files-service-deployment-xxx                 1/1     Running   0
# health-checker-deployment-xxx                1/1     Running   0   ← in default ns
# moods-api-deployment-xxx                     1/1     Running   0
# moods-service-deployment-xxx                 1/1     Running   0
# postgres-deployment-xxx                      1/1     Running   0
# server-deployment-xxx                        1/1     Running   0
# stats-api-deployment-xxx                     1/1     Running   0
# stats-service-deployment-xxx                 1/1     Running   0

# Check the ingress URL
minikube service list
minikube ip
# Access GratitudeApp at http://<minikube-ip>

# Port-forward health-checker (runs in default namespace)
kubectl port-forward svc/health-checker-cluster-ip-service -n default 8000:8000 &

# Verify health-checker summary endpoint
curl -s http://localhost:8000/api/summary | jq '{
  nodes: (.nodes | length),
  pods: (.pods | length),
  deployments: (.deployments | length)
}'
# Expected: {"nodes": 1, "pods": ~11, "deployments": ~10}
```

### 7.2 Trigger & Observe Self-Healing in Grafana

```bash
# 1. Simulate a crash-looping pod
kubectl run crashtest \
  --image=busybox \
  --restart=Always \
  -- /bin/sh -c "sleep 2; exit 1"

# 2. Watch restarts climb
kubectl get pods crashtest -w

# 3. After ~5 restarts (1–2 minutes), the healer deletes it
# Watch the Pod Restart Count panel in Grafana — you'll see the line rise then disappear

# 4. Confirm healing in the audit log
curl -s http://localhost:8000/api/healing-log | jq '.healing_log[-3:]'
# Expected: entries with action "deleted_pod" for crashtest

# 5. Clean up (if healer didn't catch it yet)
kubectl delete pod crashtest --ignore-not-found=true
```

### 7.3 Trigger & Observe HPA Scale-Out in Grafana

```bash
# 1. Deploy the load generator (hits api-gateway endpoint)
kubectl apply -f k8s-health-checker/load-generator.yaml

# 2. Watch HPA metrics in Grafana — HPA Current/Min/Max panel
# In terminal:
kubectl get hpa -n default -w
# Expected: TARGETS climbs above 70%, then REPLICAS increases from 1 → 2 → 3

# 3. Watch Available vs Desired Replicas panel in Grafana — lines rise together

# 4. Remove load generator (triggers scale-in after ~5 minutes)
kubectl delete -f k8s-health-checker/load-generator.yaml

# 5. Watch replicas scale back down
kubectl get hpa -n default -w
```

### 7.4 Trigger & Observe Prometheus Alert in Grafana

```bash
# 1. Scale a deployment to 0 replicas to trigger the alert
kubectl scale deployment entries-deployment --replicas=0 -n default

# 2. Wait ~1 minute — GratitudeAppDeploymentDegraded alert fires
# Check Prometheus Alerts:
kubectl port-forward svc/monitoring-prometheus-prometheus -n monitoring 9090:9090 &
# Open http://localhost:9090/alerts — find "GratitudeAppDeploymentDegraded"

# 3. In Grafana — check the "Active Alerts" panel
# It will list the firing alert with deployment name and severity

# 4. Check Deployment Health panel — entries-deployment turns RED (DEGRADED)

# 5. Restore the deployment
kubectl scale deployment entries-deployment --replicas=1 -n default

# 6. Wait 1–2 minutes — alert resolves, panel returns to green
```

### 7.5 Verify Slack Notification Delivery

```bash
# Send a test notification (mock mode if no webhook configured)
curl -X POST http://localhost:8000/api/notify/slack \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Sprint 6 Final E2E Test",
    "message": "All systems verified. GratitudeApp cluster healthy.",
    "severity": "info",
    "fields": {
      "Sprint": "6",
      "Environment": "Minikube",
      "Status": "PASSED"
    }
  }'

# View notification history
curl -s http://localhost:8000/api/notifications | jq '.notifications[-1]'
# Expected: notification object with title, severity, timestamp, mode (live or mock)
```

---

## 8. Step 5: Teardown

Once all screenshots are captured and the project is complete:

```bash
# Navigate to project root
cd /path/to/Capstone_Project_HeroVired

# Run automated teardown (preserves Minikube cluster data)
./scripts/99-teardown.sh

# --- OR ---

# Full teardown including Minikube cluster deletion
./scripts/99-teardown.sh --delete-cluster
```

**Manual teardown steps (if script is not used):**

```bash
# 1. Remove GratitudeApp
kubectl delete -f k8s-local/

# 2. Remove health-checker, HPA, dashboards, alerts
kubectl delete -f k8s-health-checker/deploy/
kubectl delete -f k8s-health-checker/deploy/autoscaling/

# 3. Uninstall Helm monitoring stack
helm uninstall monitoring -n monitoring
kubectl delete namespace monitoring

# 4. Stop Minikube
minikube stop
# or: minikube delete
```

---

## 10. Sprint 6 Deliverables Checklist

| # | Deliverable | File / Location | Status |
|---|-------------|-----------------|--------|
| 1 | **Sprint 6 Full Observability Dashboard** (12 panels) | [`deploy/grafana/sprint6-full-dashboard.yaml`](k8s-health-checker/deploy/grafana/sprint6-full-dashboard.yaml) | ✅ Done |
| 2 | **Node & Pod Health Dashboard** (Sprint 2, retained) | [`deploy/grafana/node-pod-health-dashboard.yaml`](k8s-health-checker/deploy/grafana/node-pod-health-dashboard.yaml) | ✅ Done |
| 3 | **User Documentation** — setup, config, API, metrics, troubleshooting | [`docs/user-guide.md`](docs/user-guide.md) | ✅ Done |
| 4 | **Alerting & Notifications Documentation** | [`docs/alerting-and-notifications.md`](docs/alerting-and-notifications.md) | ✅ Done (Sprint 5) |
| 5 | **Teardown Script** with `--delete-cluster` option | [`scripts/99-teardown.sh`](scripts/99-teardown.sh) | ✅ Done |
| 6 | **End-to-End Test** — all scenarios verified locally | Step 7 above | ⬜ Run |
| 7 | **Screenshots** — proof-of-work screenshots | |  ⬜ Capture |
| 8 | **`Readme_Local_Sprint6.md`** (this file) | `Readme_Local_Sprint6.md` | ✅ Done |

---

## Cross-Sprint Summary

| Sprint | Goal | Key Files |
|--------|------|-----------|
| **Sprint 1** | Local cluster + GratitudeApp deployment | `k8s-local/`, `Readme_Local.md` |
| **Sprint 2** | Health monitoring + Prometheus metrics | `monitor.py`, `node-pod-health-dashboard.yaml`, `gratitudeapp-alerts.yaml` |
| **Sprint 3** | Self-healing mechanisms + chaos testing | `healer.py`, `k8s_client.py`, `chaos/` |
| **Sprint 4** | HPA + node scaling + resource balancing | `balancer.py`, `hpa-gratitudeapp.yaml`, `load-generator.yaml` |
| **Sprint 5** | Slack alerting + Alertmanager routing | `slack_notifier.py`, `alertmanager-config.yaml`, `docs/alerting-and-notifications.md` |
| **Sprint 6** | Full Grafana dashboard + docs + teardown | `sprint6-full-dashboard.yaml`, `docs/user-guide.md`, `scripts/99-teardown.sh` |
