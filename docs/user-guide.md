# GratitudeApp Health-Checker — User Guide

> **Version:** Sprint 6 Final  
> **Last Updated:** 2026-10-16  
> **Audience:** DevOps engineers deploying and operating the GratitudeApp Kubernetes Health-Checker system

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Prerequisites](#3-prerequisites)
4. [Setup & Installation](#4-setup--installation)
   - 4.1 [Clone the Repository](#41-clone-the-repository)
   - 4.2 [Start Minikube Cluster](#42-start-minikube-cluster)
   - 4.3 [Deploy GratitudeApp](#43-deploy-gratitudeapp)
   - 4.4 [Deploy Monitoring Stack](#44-deploy-monitoring-stack)
   - 4.5 [Deploy Health-Checker App](#45-deploy-health-checker-app)
5. [Configuration Reference](#5-configuration-reference)
   - 5.1 [Environment Variables](#51-environment-variables)
   - 5.2 [Self-Healing Thresholds](#52-self-healing-thresholds)
   - 5.3 [Slack Webhook Configuration](#53-slack-webhook-configuration)
   - 5.4 [Alertmanager Severity Routing](#54-alertmanager-severity-routing)
   - 5.5 [HPA Scaling Configuration](#55-hpa-scaling-configuration)
6. [Usage Guide](#6-usage-guide)
   - 6.1 [API Endpoints Reference](#61-api-endpoints-reference)
   - 6.2 [Grafana Dashboards](#62-grafana-dashboards)
   - 6.3 [Triggering Manual Healing](#63-triggering-manual-healing)
   - 6.4 [Sending Test Slack Alerts](#64-sending-test-slack-alerts)
   - 6.5 [Running Chaos Experiments](#65-running-chaos-experiments)
7. [Prometheus Metrics Reference](#7-prometheus-metrics-reference)
8. [Troubleshooting Guide](#8-troubleshooting-guide)
   - 8.1 [Health-Checker Pod Not Starting](#81-health-checker-pod-not-starting)
   - 8.2 [Metrics Not Appearing in Grafana](#82-metrics-not-appearing-in-grafana)
   - 8.3 [Slack Notifications Not Delivered](#83-slack-notifications-not-delivered)
   - 8.4 [Self-Healer Not Restarting Pods](#84-self-healer-not-restarting-pods)
   - 8.5 [Alertmanager Not Firing Alerts](#85-alertmanager-not-firing-alerts)
   - 8.6 [HPA Not Scaling](#86-hpa-not-scaling)
9. [Teardown](#9-teardown)

---

## 1. Overview

The **GratitudeApp Health-Checker** is an automated Kubernetes observability and self-healing platform built for the GratitudeApp microservices cluster. It combines:

- 📊 **Real-time Prometheus metrics** for nodes, pods, and deployments
- 🛠️ **Self-healing automation** — auto-restarts `CrashLoopBackOff` / `Error` / `Evicted` pods
- ⚖️ **Resource balancing** — tracks and reports pod distribution across nodes
- 🚨 **Multi-tier Slack alerting** — routes `critical` / `warning` / `info` alerts to dedicated channels
- 📈 **Grafana dashboards** — live health, historical trends, HPA scaling, and alert history
- 🔁 **Horizontal Pod Autoscaling** — CPU-driven auto-scaling for high-traffic services

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Kubernetes Cluster                          │
│                                                                 │
│  ┌──────────────────────────────────────────────┐              │
│  │           health-checker-app (FastAPI)         │              │
│  │                                              │              │
│  │  monitor.py ──► Prometheus Gauges ──────────┼──► /metrics  │
│  │  healer.py  ──► Pod delete/restart ──────────┼──► /api/heal │
│  │  balancer.py──► Node balance metrics ────────┼──► /api/node-│
│  │  slack_notifier.py ──► Slack Webhook ────────┼    balancing │
│  └──────────────────────────────────────────────┘              │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐  │
│  │  Prometheus  │───►│ Alertmanager │───►│  Slack Channels  │  │
│  │  (scrapes    │    │ (severity    │    │  #devops-critical │  │
│  │   /metrics)  │    │  routing)    │    │  #devops-alerts   │  │
│  └──────────────┘    └──────────────┘    │  #devops-info     │  │
│          │                               └──────────────────┘  │
│          ▼                                                      │
│  ┌──────────────┐                                               │
│  │    Grafana   │  (Dashboards: node health, pod health,        │
│  │  Dashboards  │   HPA scaling, balance ratio, alert history)  │
│  └──────────────┘                                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Prerequisites

| Tool | Minimum Version | Notes |
|------|----------------|-------|
| `minikube` | v1.32+ | For local Kubernetes cluster |
| `kubectl` | v1.28+ | Kubernetes CLI |
| `helm` | v3.14+ | For deploying kube-prometheus-stack |
| `docker` | v24+ | For building container images |
| Python | 3.11+ | For healthchecker-app (in container) |

**Minikube resource requirements:**

```bash
# Minimum recommended configuration
minikube start \
  --cpus=4 \
  --memory=8192 \
  --disk-size=30g \
  --driver=docker \
  --addons=metrics-server,ingress
```

---

## 4. Setup & Installation

### 4.1 Clone the Repository

```bash
git clone <your-repo-url>
cd Capstone_Project_HeroVired
```

### 4.2 Start Minikube Cluster

```bash
# Start Minikube with adequate resources
minikube start --cpus=4 --memory=8192 --driver=docker --addons=metrics-server,ingress

# Verify cluster is ready
kubectl get nodes
# Expected: node Ready
```

### 4.3 Deploy GratitudeApp

```bash
# Deploy all GratitudeApp microservices and Postgres
kubectl apply -f k8s-local/

# Verify all pods come up (may take 2–3 minutes)
kubectl get pods -n default -w
# Expected: 10 pods Running (client, api-gateway, entries, moods-api, moods-service,
#           stats-api, stats-service, files-service, server, postgres)
```

### 4.4 Deploy Monitoring Stack

```bash
# Add Helm repo
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Install kube-prometheus-stack (Prometheus + Grafana + Alertmanager)
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  -f k8s-health-checker/deploy/prometheus/prometheus-values.yaml

# Wait for monitoring pods
kubectl get pods -n monitoring -w
# Expected: alertmanager, grafana, prometheus, kube-state-metrics pods Running

# Apply alert rules
kubectl apply -f k8s-health-checker/deploy/alerts/

# Apply Grafana dashboards
kubectl apply -f k8s-health-checker/deploy/grafana/
```

### 4.5 Deploy Health-Checker App

```bash
# Point Docker daemon to Minikube's Docker
eval $(minikube docker-env)

# Build the health-checker image
cd k8s-health-checker/healthchecker-app
docker build -t healthchecker-app:sprint6 .
cd ../..

# Deploy health-checker
kubectl apply -f k8s-health-checker/deploy/healthchecker/

# Apply HPAs for GratitudeApp scaling
kubectl apply -f k8s-health-checker/deploy/autoscaling/

# Verify health-checker is running (deploys to default namespace)
kubectl get pods -n default -l component=health-checker
kubectl logs -n default deployment/health-checker-deployment --tail=20
```

---

## 5. Configuration Reference

### 5.1 Environment Variables

Set in [`k8s-health-checker/deploy/healthchecker/deployment.yaml`](../k8s-health-checker/deploy/healthchecker/deployment.yaml):

| Variable | Default | Description |
|----------|---------|-------------|
| `TARGET_NAMESPACE` | `default` | Kubernetes namespace to monitor |
| `ENABLE_SELF_HEALING` | `true` | Enable/disable pod auto-restart logic |
| `SLACK_WEBHOOK_URL` | _(empty)_ | Slack incoming webhook URL. If unset, notifications run in mock/log mode |
| `POLL_INTERVAL_SECONDS` | `15` | How often the background poller collects metrics |

### 5.2 Self-Healing Thresholds

Defined in [`healthchecker-app/healer.py`](../k8s-health-checker/healthchecker-app/healer.py):

| Setting | Value | Description |
|---------|-------|-------------|
| Restart threshold | `5` restarts | Pod is deleted/restarted after 5+ container restarts |
| Cooldown period | `45 seconds` | Avoids restarting the same pod twice in quick succession |
| Watched phases | `CrashLoopBackOff`, `Error`, `Evicted` | Pod states that trigger healing |
| Protected namespaces | `kube-system`, `monitoring` | These namespaces are never healed |

To change thresholds, edit `healer.py` and rebuild the Docker image:

```python
# healer.py — line ~42
RESTART_THRESHOLD = 5           # change to desired value
HEALING_COOLDOWN_SECONDS = 45   # change cooldown window
```

### 5.3 Slack Webhook Configuration

```bash
# Option A: Set via kubectl secret
kubectl create secret generic slack-webhook \
  --from-literal=url="https://hooks.slack.com/services/YOUR/WEBHOOK/URL" \
  -n monitoring

# Then reference in deployment.yaml:
# - name: SLACK_WEBHOOK_URL
#   valueFrom:
#     secretKeyRef:
#       name: slack-webhook
#       key: url
```

```bash
# Option B: Quick override with patch
kubectl set env deployment/health-checker \
  SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL" \
  -n monitoring
```

When `SLACK_WEBHOOK_URL` is **not set**, the notifier runs in **mock mode** — notifications are logged to stdout and stored in the in-memory history (`GET /api/notifications`) but not delivered to Slack. This is useful for local development and testing.

### 5.4 Alertmanager Severity Routing

Configured in [`k8s-health-checker/deploy/alerts/alertmanager-config.yaml`](../k8s-health-checker/deploy/alerts/alertmanager-config.yaml):

| Severity | Slack Channel | Repeat Interval |
|----------|--------------|-----------------|
| `critical` | `#devops-critical` | 1 hour |
| `warning` | `#devops-alerts` | 4 hours |
| `info` | `#devops-info` | 12 hours |

To change channels or webhooks, edit the `alertmanager-config.yaml` and apply:

```bash
kubectl apply -f k8s-health-checker/deploy/alerts/alertmanager-config.yaml
```

### 5.5 HPA Scaling Configuration

Configured in [`k8s-health-checker/deploy/autoscaling/hpa-gratitudeapp.yaml`](../k8s-health-checker/deploy/autoscaling/hpa-gratitudeapp.yaml):

| Service | Min Replicas | Max Replicas | CPU Target |
|---------|-------------|-------------|------------|
| `api-gateway` | 1 | 3 | 70% |
| `client` | 1 | 3 | 70% |
| `entries` | 1 | 2 | 80% |

---

## 6. Usage Guide

### 6.1 API Endpoints Reference

Port-forward the health-checker service first:

```bash
kubectl port-forward svc/health-checker-cluster-ip-service -n default 8000:8000
```

Then use the following endpoints:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/healthz` | Liveness probe — returns `{"status":"ok"}` |
| `GET` | `/metrics` | Prometheus metrics (scraped automatically) |
| `GET` | `/api/nodes` | List all cluster nodes and Ready status |
| `GET` | `/api/pods` | List pods in target namespace |
| `GET` | `/api/deployments` | List deployments and replica availability |
| `GET` | `/api/summary` | Combined snapshot — nodes + pods + deployments |
| `GET` | `/api/healing-log` | Audit log of all self-healing actions (last 50) |
| `POST` | `/api/heal` | Trigger an on-demand healing scan |
| `GET` | `/api/node-balancing` | Pod distribution and cluster balance report |
| `POST` | `/api/notify/slack` | Send an on-demand Slack notification |
| `GET` | `/api/notifications` | History of dispatched Slack notifications (last 50) |

**Interactive API docs (Swagger UI):**

```bash
# Available at:
http://localhost:8000/docs
```

### 6.2 Grafana Dashboards

```bash
# Port-forward Grafana
kubectl port-forward svc/monitoring-grafana -n monitoring 3000:80

# Default credentials
Username: admin
Password: changeme
# (or check your prometheus-values.yaml for adminPassword)
```

**Available dashboards:**

| Dashboard | UID | Description |
|-----------|-----|-------------|
| Node & Pod Health | `gratitude-health-v1` | Sprint 2 — basic node/pod/deployment health |
| Full Observability (Sprint 6) | `gratitude-s6-v1` | All metrics: health + HPA + balance + alerts |

**Sprint 6 dashboard panels:**

| Panel | Type | What it shows |
|-------|------|--------------|
| Node Ready Status | Stat | Live node readiness (green/red) |
| Cluster Balance Ratio | Gauge | Pod distribution evenness (0–1.0) |
| Pods per Node | Bar Gauge | Pod count scheduled per node |
| Deployment Health | Stat | OK/DEGRADED per deployment |
| Available vs Desired Replicas | Time Series | Historical replica tracking |
| Pod Restart Count | Time Series | Historical restart trends |
| Pod Readiness Table | Table | Per-pod readiness snapshot |
| Pod Phase Distribution | Pie Chart | Running vs non-running pods |
| HPA Current/Min/Max | Time Series | Autoscaler behavior over time |
| CPU Allocatable per Node | Bar Gauge | Node capacity |
| Active Prometheus Alerts | Alert List | Firing/Pending alerts |
| Balance Ratio Trend | Time Series | Historical cluster balance |

### 6.3 Triggering Manual Healing

```bash
# On-demand healing scan (curl)
curl -X POST http://localhost:8000/api/heal

# View healing audit log
curl http://localhost:8000/api/healing-log | jq .

# Simulate a crashing pod to trigger healing
kubectl run crash-test --image=busybox \
  --restart=Always -- /bin/sh -c "exit 1"

# Watch healing kick in (pod gets deleted after 5 restarts)
kubectl get pods -w
curl http://localhost:8000/api/healing-log | jq '.healing_log[-3:]'
```

### 6.4 Sending Test Slack Alerts

```bash
# Send a test critical alert
curl -X POST http://localhost:8000/api/notify/slack \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test Critical Alert",
    "message": "Simulated critical event from health-checker API",
    "severity": "critical",
    "fields": {"Pod": "test-pod", "Namespace": "default", "Action": "Manual Test"}
  }'

# View notification history
curl http://localhost:8000/api/notifications | jq '.notifications[-5:]'
```

### 6.5 Running Chaos Experiments

```bash
# Deploy the load generator (triggers HPA scale-out)
kubectl apply -f k8s-health-checker/load-generator.yaml

# Watch HPA scale up
kubectl get hpa -n default -w

# Watch pods scale out
kubectl get pods -n default -w

# Stop load generator
kubectl delete -f k8s-health-checker/load-generator.yaml
```

---

## 7. Prometheus Metrics Reference

All metrics are exposed at `/metrics` and collected every 15 seconds.

| Metric | Labels | Type | Description |
|--------|--------|------|-------------|
| `healthchecker_node_ready` | `node` | Gauge | 1=Ready, 0=NotReady |
| `healthchecker_pod_restarts_total` | `namespace`, `pod` | Gauge | Container restart count |
| `healthchecker_pod_phase_running` | `namespace`, `pod` | Gauge | 1=Running, 0=other |
| `healthchecker_pod_ready` | `namespace`, `pod` | Gauge | 1=Ready condition True |
| `healthchecker_deployment_available_replicas` | `namespace`, `deployment` | Gauge | Available replica count |
| `healthchecker_deployment_desired_replicas` | `namespace`, `deployment` | Gauge | Desired replica count |
| `healthchecker_deployment_all_replicas_available` | `namespace`, `deployment` | Gauge | 1=all OK, 0=DEGRADED |
| `healthchecker_node_pod_count` | `node` | Gauge | Pods scheduled per node |
| `healthchecker_node_cpu_capacity_cores` | `node` | Gauge | Allocatable CPU cores |
| `healthchecker_cluster_balance_ratio` | _(none)_ | Gauge | min/max pod count ratio |

**Example PromQL queries:**

```promql
# All degraded deployments
healthchecker_deployment_all_replicas_available{namespace="default"} == 0

# Pods restarted more than 5 times
healthchecker_pod_restarts_total{namespace="default"} > 5

# Cluster balance under 0.6 (imbalanced)
healthchecker_cluster_balance_ratio < 0.6

# HPA scale events (kube-state-metrics)
kube_horizontalpodautoscaler_status_current_replicas{namespace="default"}
```

---

## 8. Troubleshooting Guide

### 8.1 Health-Checker Pod Not Starting

```bash
# Check pod status
kubectl get pods -n default -l component=health-checker

# Describe pod for events
kubectl describe pod -n default -l component=health-checker

# Check logs
kubectl logs -n default deployment/health-checker-deployment --tail=50

# Common causes:
# - ImagePullBackOff: Image not built in Minikube's Docker daemon
#   Fix: eval $(minikube docker-env) && docker build -t healthchecker-app:sprint6 .
# - CrashLoopBackOff: kubeconfig misconfigured — check KUBECONFIG env or ServiceAccount
```

### 8.2 Metrics Not Appearing in Grafana

```bash
# 1. Check Prometheus can scrape the health-checker
kubectl port-forward svc/monitoring-prometheus-prometheus -n monitoring 9090:9090
# Open http://localhost:9090/targets — look for health-checker target

# 2. Verify ServiceMonitor exists
kubectl get servicemonitor -n monitoring

# 3. Manually check /metrics endpoint
kubectl port-forward svc/health-checker-cluster-ip-service -n default 8000:8000
curl http://localhost:8000/metrics | grep healthchecker_

# 4. Check Grafana can reach Prometheus data source
# Grafana → Connections → Data Sources → Prometheus → Test
```

### 8.3 Slack Notifications Not Delivered

```bash
# 1. Check if webhook URL is set
kubectl get deployment health-checker-deployment -n default \
  -o jsonpath='{.spec.template.spec.containers[0].env}' | jq .

# 2. Check health-checker logs for "MOCK mode" messages
kubectl logs -n default deployment/health-checker-deployment | grep -i "mock\|slack\|webhook"

# 3. Test webhook directly
curl -X POST "$SLACK_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d '{"text": "Test from health-checker"}'

# 4. Check notification history (mock mode stores locally)
curl http://localhost:8000/api/notifications | jq '.notifications[0]'
```

### 8.4 Self-Healer Not Restarting Pods

```bash
# 1. Verify ENABLE_SELF_HEALING is true
kubectl get deployment health-checker-deployment -n default \
  -o jsonpath='{.spec.template.spec.containers[0].env}' | jq .

# 2. Check healer audit log
curl http://localhost:8000/api/healing-log | jq .

# 3. Check for RBAC issues — healer needs pod/delete permission
kubectl auth can-i delete pods --as=system:serviceaccount:default:health-checker -n default

# 4. Trigger on-demand heal
curl -X POST http://localhost:8000/api/heal

# 5. Simulate crashing pod
kubectl run crashtest --image=busybox --restart=Always -- /bin/sh -c "exit 1"
# Wait ~2 minutes (restart threshold=5, check every 15s)
```

### 8.5 Alertmanager Not Firing Alerts

```bash
# 1. Check PrometheusRule was picked up
kubectl get prometheusrule -n monitoring
kubectl describe prometheusrule gratitudeapp-health-alerts -n monitoring

# 2. Check Prometheus rules loaded
kubectl port-forward svc/monitoring-prometheus-prometheus -n monitoring 9090:9090
# http://localhost:9090/rules — should show gratitudeapp-health-alerts groups

# 3. Check Alertmanager config applied
kubectl get secret alertmanager-monitoring-alertmanager -n monitoring -o yaml

# 4. Manually trigger an alert test
kubectl scale deployment client-deployment --replicas=0 -n default
# Wait 1m+ — GratitudeAppDeploymentDegraded alert should fire
# Restore:
kubectl scale deployment client-deployment --replicas=1 -n default
```

### 8.6 HPA Not Scaling

```bash
# 1. Verify metrics-server is running
kubectl top pods -n default

# 2. Check HPA status
kubectl describe hpa -n default

# 3. Verify resource requests are set on the deployment
kubectl get deployment api-gateway-deployment -n default \
  -o jsonpath='{.spec.template.spec.containers[0].resources}'

# 4. Deploy load generator to trigger scale-out
kubectl apply -f k8s-health-checker/load-generator.yaml
kubectl get hpa -n default -w
```

---

## 9. Teardown

To fully remove all resources from the cluster:

```bash
# Remove GratitudeApp
kubectl delete -f k8s-local/

# Remove health-checker and autoscaling
kubectl delete -f k8s-health-checker/deploy/

# Remove monitoring stack
helm uninstall monitoring -n monitoring
kubectl delete namespace monitoring

# Stop Minikube
minikube stop

# (Optional) Delete Minikube cluster entirely
minikube delete
```

Or run the automated teardown script:

```bash
chmod +x scripts/99-teardown.sh
./scripts/99-teardown.sh
```

---

*For alert setup and Slack webhook configuration details, see [`docs/alerting-and-notifications.md`](alerting-and-notifications.md).*  
*For EKS migration steps, see [`docs/minikube-to-eks-migration.md`](minikube-to-eks-migration.md).*
