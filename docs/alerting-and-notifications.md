# Alerting and Notification System Guide — Sprint 5

## 1. Overview

The GratitudeApp monitoring and alerting architecture uses a two-tier notification system to keep DevOps teams informed of cluster events in real time:

1. **Self-Healing Real-Time Alerts (Health-Checker):**
   When the automated recovery module detects failures (such as `CrashLoopBackOff`, `Evicted` pods, or unready deployment replicas) and takes remediation action, it immediately dispatches a formatted Slack notification detailing what pod was remediated, the reason, and the result.

2. **Infrastructure & Metric Threshold Alerts (Prometheus + Alertmanager):**
   Longer-term infrastructure state changes (e.g. `NodeNotReady` > 2m, `GratitudeAppDeploymentDegraded` > 1m, `PodHighRestartCount` > 5) are evaluated by Prometheus rules and routed by Alertmanager to dedicated Slack channels based on severity.

```
┌─────────────────────────────────┐       ┌─────────────────────────────────┐
│     Prometheus Alert Rules      │       │  Health-Checker Auto-Healer     │
│   (NodeNotReady, Degraded, etc) │       │   (CrashLoop, Evicted Purge)    │
└────────────────┬────────────────┘       └────────────────┬────────────────┘
                 │ Firing alerts                           │ Remediations
                 ▼                                         ▼
┌─────────────────────────────────┐       ┌─────────────────────────────────┐
│          Alertmanager           │       │    Slack Notifier Module        │
│   - Route by severity           │       │    (slack_notifier.py)          │
│   - Grouping & inhibition       │       │    - Formatted attachments      │
│   - Multi-channel dispatch      │       │    - Mock/Live delivery         │
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

## 2. Severity Levels & Channel Mapping

| Severity | Target Channel | Color Code | Examples | Repeat Interval |
|----------|----------------|------------|----------|-----------------|
| **Critical** | `#devops-critical` | Danger (`#E01E5A` Red) | `NodeNotReady`, Cluster-wide outages, Persistent DB disconnection | 10 minutes |
| **Warning** | `#devops-alerts` | Warning (`#ECB22E` Amber) | `GratitudeAppDeploymentDegraded`, `PodHighRestartCount` | 1 hour |
| **Healing** | `#devops-alerts` | Info (`#36C5F0` Blue) | Pod restarted from `CrashLoopBackOff`, Evicted pod purged | Real-time on event |
| **Info** | `#devops-info` | Good (`#2EB67D` Green) | Resolved alerts, successful autoscaler rebalance | 2 hours |

---

## 3. Configuring Slack Webhook

### 3.1 Creating the Incoming Webhook in Slack
1. Open [Slack API: Your Apps](https://api.slack.com/apps) and create or select an app for your workspace.
2. Under **Features**, select **Incoming Webhooks** and activate it.
3. Click **Add New Webhook to Workspace** and select your alert channel (e.g., `#devops-alerts`).
4. Copy the Webhook URL (format: `https://hooks.slack.com/services/T.../B.../X...`).

### 3.2 Setting the Secret in Kubernetes
Store the webhook securely as a Kubernetes secret:

```bash
kubectl create secret generic slack-webhook-secret \
  --from-literal=url='https://hooks.slack.com/services/YOUR/WEBHOOK/URL' \
  -n default
```

Or pass it into the health-checker deployment via environment variable `SLACK_WEBHOOK_URL`:

```yaml
env:
  - name: SLACK_WEBHOOK_URL
    valueFrom:
      secretKeyRef:
        name: slack-webhook-secret
        key: url
```

*(Note: If `SLACK_WEBHOOK_URL` is empty or set to `mock`, the health-checker operates in simulated mode, safely logging notifications to console and `/api/notifications` without error).*

---

## 4. Customizing Alert Rules

Alert definitions are maintained in [`k8s-health-checker/deploy/alerts/gratitudeapp-alerts.yaml`](../k8s-health-checker/deploy/alerts/gratitudeapp-alerts.yaml).

To modify a threshold (e.g. alert immediately if pod restarts exceed 3):
```yaml
- alert: PodHighRestartCount
  expr: healthchecker_pod_restarts_total{namespace="default"} > 3
  for: 0m
  labels:
    severity: warning
  annotations:
    summary: "Pod {{ $labels.pod }} restarted {{ $value }} times"
```

Apply updates:
```bash
kubectl apply -f k8s-health-checker/deploy/alerts/gratitudeapp-alerts.yaml
```

---

## 5. Testing Alert Delivery

### 5.1 Test Health-Checker Slack Notifier API
Send a test alert directly via the health-checker API:

```bash
curl -X POST http://localhost:8000/api/notify/slack \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Manual Health Check Notification",
    "message": "Testing Slack alerting pipeline from devops workstation.",
    "severity": "info",
    "fields": {"Status": "Healthy", "Cluster": "Minikube"}
  }'
```

Inspect dispatched notification log:
```bash
curl -s http://localhost:8000/api/notifications | python3 -m json.tool
```

### 5.2 Test Self-Healing Alert Delivery
Trigger a `CrashLoopBackOff` event:
```bash
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-crash-notifier
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: test-crash-notifier
  template:
    metadata:
      labels:
        app: test-crash-notifier
    spec:
      containers:
      - name: crash
        image: busybox:1.36
        command: ["/bin/sh", "-c", "exit 1"]
EOF
```

Observe the auto-healer deleting the pod and sending the Slack alert. Check the log:
```bash
curl -s http://localhost:8000/api/notifications | python3 -m json.tool | head -30
```

Clean up:
```bash
kubectl delete deployment test-crash-notifier -n default
```
