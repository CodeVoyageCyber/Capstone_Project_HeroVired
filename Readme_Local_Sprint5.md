# Sprint 5 — Alerting and Notification System Integration: Step-by-Step Guide

**Goal:** Implement a comprehensive alerting and notification system to keep the DevOps team informed of critical cluster events, degraded service replicas, and automated self-healing actions via Slack incoming webhooks and Alertmanager multi-severity routing.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [What's New in Sprint 5](#2-whats-new-in-sprint-5)
3. [Notification Architecture](#3-notification-architecture)
4. [Step 1: Slack Notifier Module in Health-Checker](#4-step-1-slack-notifier-module-in-health-checker)
5. [Step 2: Alertmanager Multi-Tier Slack Routing](#5-step-2-alertmanager-multi-tier-slack-routing)
6. [Step 3: Build & Deploy Health-Checker (`sprint5`)](#6-step-3-build--deploy-health-checker-sprint5)
7. [Step 4: End-to-End Verification & Testing](#7-step-4-end-to-end-verification--testing)
   - 7.1 [Test Direct Notification Endpoint](#71-test-direct-notification-endpoint)
   - 7.2 [Test Self-Healing Notification Delivery](#72-test-self-healing-notification-delivery)
   - 7.3 [Test Alertmanager Deployment Alert Delivery](#73-test-alertmanager-deployment-alert-delivery)
   - 7.4 [Verify Notification History Endpoint](#74-verify-notification-history-endpoint)
8. [Step-by-Step Screenshot Guide](#8-step-by-step-screenshot-guide)
9. [Sprint 5 Deliverables Checklist](#9-sprint-5-deliverables-checklist)

---

## 1. Prerequisites

Before beginning Sprint 5, verify that your cluster has the GratitudeApp and monitoring stack running:

```bash
# 1. Minikube is running
minikube status

# 2. Monitoring stack active
kubectl get pods -n monitoring
# Expected: Prometheus, Grafana, Alertmanager pods Running

# 3. GratitudeApp pods healthy
kubectl get pods -n default
# Expected: All services Running
```

---

## 2. What's New in Sprint 5

| Component | Description | Implementation |
|-----------|-------------|----------------|
| **Slack Notifier Module** | Dispatches real-time color-coded Slack Block Kit messages for alerts and self-healing actions; includes mock/simulation mode when no webhook is set | [`healthchecker-app/slack_notifier.py`](k8s-health-checker/healthchecker-app/slack_notifier.py) |
| **Self-Healing Integration** | Automatically dispatches a Slack alert whenever `healer.py` restarts a pod or purges an evicted pod | [`healthchecker-app/healer.py`](k8s-health-checker/healthchecker-app/healer.py) |
| **Alertmanager Routing** | Routes alerts across multiple severity tiers (`critical`, `warning`, `info`) to designated Slack channels | [`k8s-health-checker/deploy/alerts/alertmanager-config.yaml`](k8s-health-checker/deploy/alerts/alertmanager-config.yaml) |
| **Direct Notifier API** | `POST /api/notify/slack` allows sending test or on-demand notifications | [`healthchecker-app/main.py`](k8s-health-checker/healthchecker-app/main.py) |
| **Notification Audit Log** | `GET /api/notifications` returns history of recently dispatched alert notifications | [`healthchecker-app/main.py`](k8s-health-checker/healthchecker-app/main.py) |
| **Alerting Documentation** | Detailed guide on setting up webhooks, severity tiers, and troubleshooting | [`docs/alerting-and-notifications.md`](docs/alerting-and-notifications.md) |

---

## 3. Notification Architecture

```
┌─────────────────────────────────┐       ┌─────────────────────────────────┐
│     Prometheus Alert Rules      │       │  Health-Checker Auto-Healer     │
│   (NodeNotReady, Degraded, etc) │       │   (CrashLoop, Evicted Purge)    │
└────────────────┬────────────────┘       └────────────────┬────────────────┘
                 │ Firing alerts                           │ Remediations
                 ▼                                         ▼
┌─────────────────────────────────┐       ┌─────────────────────────────────┐
│          Alertmanager           │       │    Slack Notifier Module        │
│   - Multi-tier severity routing │       │    (slack_notifier.py)          │
│   - Inhibit rules & grouping    │       │    - Block Kit color formatting │
│   - Channel fan-out             │       │    - Mock & Live webhook modes  │
└────────────────┬────────────────┘       └────────────────┬────────────────┘
                 │                                         │
                 └───────────────────┬─────────────────────┘
                                     │
                                     ▼
                  ┌─────────────────────────────────────┐
                  │          Slack Channels             │
                  │   🚨 #devops-critical (Danger)      │
                  │   ⚠️ #devops-alerts   (Warning)     │
                  │   🛠️ #devops-alerts   (Healing)     │
                  └─────────────────────────────────────┘
```

---

## 4. Step 1: Slack Notifier Module in Health-Checker

**File:** [`k8s-health-checker/healthchecker-app/slack_notifier.py`](k8s-health-checker/healthchecker-app/slack_notifier.py)

Key capabilities:
- **`send_slack_message(title, message, severity, fields, webhook_url)`**: Formats an interactive Slack attachment with color coding (`#E01E5A` danger for critical, `#ECB22E` warning, `#36C5F0` healing, `#2EB67D` info).
- **`send_healing_notification(action, pod, namespace, reason, result, details)`**: Formats automated pod remediation notifications with target pod, trigger reason, and action taken.
- **Graceful Fallback / Simulation:** If `SLACK_WEBHOOK_URL` is not set or set to `mock`, it safely logs the notification to memory and console, allowing complete end-to-end testing without external network dependencies.

---

## 5. Step 2: Alertmanager Multi-Tier Slack Routing

**File:** [`k8s-health-checker/deploy/alerts/alertmanager-config.yaml`](k8s-health-checker/deploy/alerts/alertmanager-config.yaml)

Configures Alertmanager routing rules:
- **`severity: critical`** ➔ Receiver `slack-critical` (`#devops-critical`, repeat every 10m)
- **`severity: warning`** ➔ Receiver `slack-warning` (`#devops-alerts`, repeat every 1h)
- **`severity: info`** ➔ Receiver `slack-info` (`#devops-info`, repeat every 2h)

Apply the Alertmanager configuration Secret:

```bash
kubectl apply -f k8s-health-checker/deploy/alerts/alertmanager-config.yaml
```

Verify that Alertmanager reloads its configuration:

```bash
kubectl logs -n monitoring alertmanager-monitoring-kube-prometheus-alertmanager-0 -c alertmanager --tail=20
```

### Screenshot — Alertmanager Configuration Applied

> showing `kubectl apply -f k8s-health-checker/deploy/alerts/alertmanager-config.yaml` and Alertmanager logs confirming reload._
<img width="3028" height="656" alt="image" src="https://github.com/user-attachments/assets/a1090ed9-5c4c-4ba8-bc4d-10a7eb6fc9ed" />

---

## 6. Step 3: Build & Deploy Health-Checker (`sprint5`)

Build the updated image inside Minikube:

```bash
minikube image build -t health-checker:sprint5 k8s-health-checker/healthchecker-app/
```

Apply the updated deployment manifest:

```bash
kubectl apply -f k8s-health-checker/deploy/healthchecker/deployment.yaml
kubectl rollout status deployment/health-checker-deployment -n default
```

Verify the new pod is running:

```bash
kubectl get pods -n default -l component=health-checker
```

### Screenshot — Health-Checker Sprint 5 Pod Running

> showing `kubectl rollout status` and pod running with `health-checker:sprint5`._
<img width="2232" height="386" alt="image" src="https://github.com/user-attachments/assets/56e57f79-f1cd-4b9a-93cc-cc540f1127f4" />

---

## 7. Step 4: End-to-End Verification & Testing

Start port-forwarding the health-checker:

```bash
kubectl port-forward svc/health-checker-cluster-ip-service 8000:8000 -n default &
```

### 7.1 Test Direct Notification Endpoint

Dispatch a test alert via `POST /api/notify/slack`:

```bash
curl -X POST http://localhost:8000/api/notify/slack \
  -H "Content-Type: application/json" \
  -d '{
    "title": "GratitudeApp Production Alert",
    "message": "Manual alert test from DevOps workstation.",
    "severity": "warning",
    "fields": {
      "Environment": "Production-Demo",
      "Cluster": "Minikube",
      "Component": "API-Gateway"
    }
  }' | python3 -m json.tool
```

Expected output:
```json
{
    "status": "ok",
    "notification": {
        "delivered": true,
        "details": "Delivered to mock notifier (SLACK_WEBHOOK_URL not configured)",
        "fields": {
            "Cluster": "Minikube",
            "Component": "API-Gateway",
            "Environment": "Production-Demo"
        },
        "message": "Manual alert test from DevOps workstation.",
        "severity": "warning",
        "status": "simulated",
        "target_channel": "#devops-alerts",
        "title": "GratitudeApp Production Alert"
    }
}
```

### Screenshot — Direct Slack Notification Dispatched

> terminal showing the curl `POST /api/notify/slack` response._
<img width="1844" height="1164" alt="image" src="https://github.com/user-attachments/assets/53c2df8e-7adf-4b17-ac9e-1edf50ecc797" />

---

### 7.2 Test Self-Healing Notification Delivery

Deploy a test workload that immediately fails to trigger auto-healing:

```bash
cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-healing-notifier
  namespace: default
  labels:
    app: test-healing-notifier
spec:
  replicas: 1
  selector:
    matchLabels:
      app: test-healing-notifier
  template:
    metadata:
      labels:
        app: test-healing-notifier
    spec:
      containers:
      - name: failing-app
        image: busybox:1.36
        command: ["/bin/sh", "-c", "echo 'Simulating fatal error'; exit 1"]
EOF
```

Wait ~15–20 seconds for the health-checker to detect and remediate the pod, then inspect the health-checker logs:

```bash
kubectl logs -n default -l component=health-checker --tail=15
```

Expected log:
```text
INFO:healer:Self-healing action: {'action': 'restart_deployment_pod', 'reason': 'Error', ...}
INFO:slack_notifier:[MOCK SLACK] 🛠️ Self-Healing Action: Restart Deployment Pod: Pod *test-healing-notifier-...* was remediated due to *Error*.
```

Check the notifications endpoint:

```bash
curl -s http://localhost:8000/api/notifications | python3 -m json.tool | head -35
```

Clean up the test deployment:

```bash
kubectl delete deployment test-healing-notifier -n default
```

### Screenshot — Self-Healing Notification Delivery

> showing `kubectl logs` displaying the auto-recovery event and the resulting Slack notification record._
<img width="1896" height="552" alt="image" src="https://github.com/user-attachments/assets/ba056dd3-9f85-4c57-88a5-1cb68b3344c3" />
<img width="1804" height="1764" alt="image" src="https://github.com/user-attachments/assets/17c908fb-2eb9-4e4d-907a-0c307f8c8fe1" />

---

### 7.3 Test Alertmanager Deployment Alert Delivery

Scale a deployment to 0 to trigger Prometheus rule `GratitudeAppDeploymentDegraded`:

```bash
kubectl scale deployment client-deployment --replicas=0 -n default
```

Wait ~60 seconds, then check Alertmanager UI (`http://localhost:9093`):

```bash
kubectl port-forward svc/monitoring-kube-prometheus-alertmanager 9093:9093 -n monitoring &
# Open: http://localhost:9093
```

Notice the alert firing under receiver `slack-warning`:
- **Alert:** `GratitudeAppDeploymentDegraded`
- **Severity:** `warning`
- **Receiver:** `slack-warning`

Restore the deployment:

```bash
kubectl scale deployment client-deployment --replicas=1 -n default
kubectl rollout status deployment/client-deployment -n default
```

### Screenshot — Alertmanager UI Firing Alert

> Alertmanager (`http://localhost:9093`) showing `GratitudeAppDeploymentDegraded` active and routed to `slack-warning`._
<img width="2600" height="1252" alt="image" src="https://github.com/user-attachments/assets/0a901c2b-cee0-486f-8af7-2a4a3c88a41b" />

---

### 7.4 Verify Notification History Endpoint

Query `/api/notifications` to see all alert records:

```bash
curl -s http://localhost:8000/api/notifications | python3 -m json.tool
```

### Screenshot — `/api/notifications` JSON Output

> showing the formatted list of all dispatched notifications._
<img width="1956" height="1840" alt="image" src="https://github.com/user-attachments/assets/dfc6ed79-e65c-4832-8cdd-ffc238c24afb" />

---

## 8. Sprint 5 Deliverables Checklist

### Slack Integration & Health-Checker Notifier
- [x] Implemented [`slack_notifier.py`](k8s-health-checker/healthchecker-app/slack_notifier.py) with Block Kit formatting, multi-severity colors, and mock/live delivery
- [x] Integrated real-time Slack alerts into [`healer.py`](k8s-health-checker/healthchecker-app/healer.py)
- [x] Added `POST /api/notify/slack` and `GET /api/notifications` to [`main.py`](k8s-health-checker/healthchecker-app/main.py)
- [x] Updated [`deployment.yaml`](k8s-health-checker/deploy/healthchecker/deployment.yaml) with `SLACK_WEBHOOK_URL` and `SLACK_CHANNEL`

### Alertmanager Multi-Tier Routing
- [x] Created [`alertmanager-config.yaml`](k8s-health-checker/deploy/alerts/alertmanager-config.yaml) with `critical`, `warning`, and `info` Slack receivers
- [x] Configured inhibition rules to suppress warnings when critical alerts fire
- [x] Verified alert routing to dedicated Slack channels (`#devops-critical`, `#devops-alerts`, `#devops-info`)

### Documentation & Testing
- [x] Created [`docs/alerting-and-notifications.md`](docs/alerting-and-notifications.md) covering webhook setup, routing tables, and customization
- [x] Validated direct Slack notifications, self-healing notifications, and Alertmanager alert delivery
