# Sprint 3 — Self-Healing Mechanisms & Chaos Testing: Step-by-Step Guide (Local / Minikube)

**Goal:** Automate pod recovery processes for GratitudeApp services, implement automated cleanup for pods stuck in `CrashLoopBackOff` or `Evicted` states, configure AWS FIS chaos engineering RBAC & templates, and provide structured audit logging of every healing action via `/api/healing-log` and Prometheus metrics.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [What's New in Sprint 3](#2-whats-new-in-sprint-3)
3. [Self-Healing Architecture & Logic](#3-self-healing-architecture--logic)
4. [Code Implementation Details](#4-code-implementation-details)
   - 4.1 [`healer.py` — Auto-Recovery Module](k8s-health-checker/healthchecker-app/healer.py)
   - 4.2 [`k8s_client.py` — Pod Deletion Helper](k8s-health-checker/healthchecker-app/k8s_client.py)
   - 4.3 [`monitor.py` — Integration into Polling Loop](k8s-health-checker/healthchecker-app/monitor.py)
   - 4.4 [`main.py` — New Audit Endpoints](k8s-health-checker/healthchecker-app/main.py)
5. [Apply AWS FIS Chaos RBAC Manifests](#5-apply-aws-fis-chaos-rbac-manifests)
6. [Build Docker Image (`health-checker:sprint3`)](#6-build-docker-image-health-checkersprint3)
7. [Deploy the Updated Health-Checker](#7-deploy-the-updated-health-checker)
8. [Verify Health-Checker & Endpoints](#8-verify-health-checker--endpoints)
9. [Chaos Engineering & Self-Healing Scenarios](#9-chaos-engineering--self-healing-scenarios)
   - 9.1 Scenario 1: AWS FIS Chaos Experiment Template Review
   - 9.2 Scenario 2: CrashLoopBackOff Pod Detection & Auto-Recovery
   - 9.3 Scenario 3: Evicted Pod Automated Cleanup
   - 9.4 Scenario 4: CPU Stress Simulation on `server-deployment`
10. [Verify Audit Logging & Prometheus Metrics](#10-verify-audit-logging--prometheus-metrics)
11. [Step-by-Step Screenshot Guide](#11-step-by-step-screenshot-guide)
12. [Sprint 3 Deliverables Checklist](#12-sprint-3-deliverables-checklist)

---

## 1. Prerequisites

Before starting Sprint 3, ensure your local Minikube cluster has the GratitudeApp and monitoring stack running from Sprint 1 & 2:

```bash
# 1. Minikube is running
minikube status
# Expected: host: Running, kubelet: Running, apiserver: Running

# 2. GratitudeApp pods are healthy
kubectl get pods -n default
# Expected: All services (client, api-gateway, server, postgres, etc.) Running

# 3. Prometheus & Grafana stack running
kubectl get pods -n monitoring
# Expected: Prometheus, Grafana, alertmanager pods Running
```

---

## 2. What's New in Sprint 3

### New Capabilities

| Feature | Description | Implementation |
|---------|-------------|----------------|
| **Auto-Recovery** | Automatically restarts/deletes unresponsive or failing GratitudeApp pods owned by Deployments so ReplicaSets recreate fresh healthy pods | `healer.py` (`scan_and_heal`) |
| **CrashLoopBackOff Cleanup** | Identifies containers in `CrashLoopBackOff` or `Error` state and triggers remediation | `healer.py` (`diagnose_pod`) |
| **Evicted Pod Purge** | Automatically detects and cleans up pods terminated with `Evicted` status (due to disk/memory pressure) | `healer.py` |
| **Workload Cooldown** | 45-second cooldown per workload prevents flapping and excessive restarts | `_cooldown_tracker` |
| **Structured Audit Logging** | Detailed record of every recovery action (`timestamp`, `pod`, `namespace`, `action`, `reason`, `result`, `details`) | `GET /api/healing-log` |
| **Manual Healing Trigger** | On-demand trigger to force an immediate self-healing scan | `POST /api/heal` |
| **Prometheus Counter** | Tracks cumulative healing actions by reason and result | `healthchecker_healing_actions_total` |
| **AWS FIS Integration** | RBAC permissions and AWS FIS experiment template (`fis-template.json`) for CPU stress on `server-deployment` | `chaos/` manifests |

---

## 3. Self-Healing Architecture & Logic

```
   ┌─────────────────────────────────────────────────────────────┐
   │            Background Loop (Every 15s)                      │
   └──────────────────────────────┬──────────────────────────────┘
                                  │
                                  ▼
   ┌─────────────────────────────────────────────────────────────┐
   │        Fetch Pods in namespace (default: "default")         │
   └──────────────────────────────┬──────────────────────────────┘
                                  │
                                  ▼
      Is Pod Evicted? ────► [YES] ──► Delete Pod ──► Log Audit ("cleanup_evicted_pod")
             │ [NO]
             ▼
      Is Container in CrashLoopBackOff / Error?
      OR Unready with Restarts >= 5?
             │
             ├──► [YES] ──► Is Pod owned by ReplicaSet/Deployment?
             │                     │ [YES]
             │                     ▼
             │              Within 45s cooldown?
             │                     │ [NO]
             │                     ▼
             │              Delete Pod (ReplicaSet spins new healthy pod)
             │                     │
             │                     ▼
             │              Record Audit Log + Increment Prometheus Metric
             │
             └──► [NO]  ──► No action required
```

---

## 4. Code Implementation Details

### 4.1 Self-Healing Module: [`k8s-health-checker/healthchecker-app/healer.py`](k8s-health-checker/healthchecker-app/healer.py)

Contains the core self-healing algorithms, audit logging buffer, and cooldown tracker.

Key functions:
- `diagnose_pod(pod)`: Inspects pod phase, status reasons, container waiting states (`CrashLoopBackOff`, `Error`, `CreateContainerConfigError`), and restart thresholds.
- `scan_and_heal(core, namespace)`: Scans all pods, filters deployment-backed workloads, checks cooldown, deletes faulty pods, and writes audit records.
- `get_healing_audit_log(limit)`: Returns structured records of all actions taken.
- `record_audit(...)`: Adds log entry and increments the `healthchecker_healing_actions_total` Prometheus counter.

### 4.2 Pod Deletion Helper: [`k8s-health-checker/healthchecker-app/k8s_client.py`](k8s-health-checker/healthchecker-app/k8s_client.py)

Adds the deletion helper method:

```python
def delete_pod(core: client.CoreV1Api, name: str, namespace: str = "default"):
    """Delete a pod so its parent ReplicaSet/Deployment can recreate it."""
    return core.delete_namespaced_pod(name=name, namespace=namespace)
```

### 4.3 Background Integration: [`k8s-health-checker/healthchecker-app/monitor.py`](k8s-health-checker/healthchecker-app/monitor.py)

Integrates `scan_and_heal` directly into the background monitoring poller thread (runs every 15 seconds):

```python
if enable_healing:
    core, _ = get_clients()
    scan_and_heal(core, namespace)
```

### 4.4 Audit Endpoints: [`k8s-health-checker/healthchecker-app/main.py`](k8s-health-checker/healthchecker-app/main.py)

Exposes two new endpoints:
- `GET /api/healing-log`: Returns recent healing actions with timestamp, target pod, reason, and result.
- `POST /api/heal`: Allows initiating an on-demand healing scan.

---

## 5. Apply AWS FIS Chaos RBAC Manifests

AWS FIS (Fault Injection Simulator) requires specific service accounts and roles within Kubernetes to inject faults (e.g. CPU stress, terminate pods, network latency).

The manifests are located in `k8s-health-checker/chaos/`:
1. `rbac.yml`: Creates ServiceAccount `fis-sa`, Role `fis-role`, and RoleBinding `fis-role-binding`.
2. `fis-sa-cluster-admin.yml`: Binds `fis-sa` to `cluster-admin`.
3. `fis-experiement-cluster-admin.yml`: Binds `fis-experiment` to `cluster-admin`.

Apply them to your cluster:

```bash
kubectl apply -f k8s-health-checker/chaos/rbac.yml
kubectl apply -f k8s-health-checker/chaos/fis-sa-cluster-admin.yml
kubectl apply -f k8s-health-checker/chaos/fis-experiement-cluster-admin.yml
```

Expected output:
```text
serviceaccount/fis-sa created
role.rbac.authorization.k8s.io/fis-role created
rolebinding.rbac.authorization.k8s.io/fis-role-binding created
clusterrolebinding.rbac.authorization.k8s.io/fis-sa-cluster-admin created
clusterrolebinding.rbac.authorization.k8s.io/fis-experiment-cluster-admin created
```

Verify service account creation:
```bash
kubectl get sa -n default fis-sa
```

### Screenshot — AWS FIS RBAC Applied
> showing `kubectl apply` output for the three chaos RBAC manifests and `kubectl get sa -n default fis-sa`._
<img width="3048" height="402" alt="image" src="https://github.com/user-attachments/assets/3c89655f-b368-4b08-b555-5203f67fcf59" />

---

## 6. Build Docker Image (`health-checker:sprint3`)

Because Minikube uses the containerd runtime, use `minikube image build` to build the image directly inside Minikube's image registry:

```bash
minikube image build -t health-checker:sprint3 k8s-health-checker/healthchecker-app/
```

Verify the image is in Minikube:

```bash
minikube image ls | grep health-checker
# Expected:
# docker.io/library/health-checker:sprint3
```

---

## 7. Deploy the Updated Health-Checker

Update the deployment manifest:

```bash
kubectl apply -f k8s-health-checker/deploy/healthchecker/deployment.yaml
```

Wait for the new pod to roll out:

```bash
kubectl rollout status deployment/health-checker-deployment -n default
```

Verify the new pod is running:

```bash
kubectl get pods -n default -l component=health-checker
```

Inspect logs to confirm self-healing poller started:

```bash
kubectl logs -n default -l component=health-checker --tail=25
# Expected log lines:
# INFO:monitor: ...
# Application startup complete.
```

### Screenshot — Health-Checker Sprint 3 Pod Running & Logs

> showing `kubectl rollout status` and `kubectl logs` confirming Sprint 3 health-checker is running._
<img width="2562" height="694" alt="image" src="https://github.com/user-attachments/assets/2117281a-e462-47a6-b176-0cfbfd93b3e0" />

---

## 8. Verify Health-Checker & Endpoints

Start port-forwarding the health-checker:

```bash
kubectl port-forward svc/health-checker-cluster-ip-service 8000:8000 -n default
```

### 8.1 Test `/api/healing-log` (Initial State)

```bash
curl -s http://localhost:8000/api/healing-log | python3 -m json.tool
```

Expected output:
```json
{
    "healing_log": []
}
```

### 8.2 Test `/metrics` for Self-Healing Counter

```bash
curl -s http://localhost:8000/metrics | grep "healthchecker_healing_actions"
```

Expected output:
```text
# HELP healthchecker_healing_actions_total Total number of self-healing actions performed
# TYPE healthchecker_healing_actions_total counter
```

---

## 9. Chaos Engineering & Self-Healing Scenarios

### 9.1 Scenario 1: AWS FIS Chaos Experiment Template Review

Inspect [`k8s-health-checker/chaos/fis-template.json`](k8s-health-checker/chaos/fis-template.json):

```json
{
  "description": "CPU Stress on pods in server-deployment",
  "targets": {
    "serverPods": {
      "resourceType": "aws:eks:pod",
      "selectionMode": "COUNT(1)",
      "parameters": {
        "clusterIdentifier": "mck-demo",
        "namespace": "default",
        "selectorType": "deploymentName",
        "selectorValue": "server-deployment"
      }
    }
  },
  "actions": {
    "cpuStress": {
      "actionId": "aws:eks:pod-cpu-stress",
      "description": "Introduce CPU load",
      "parameters": {
        "kubernetesServiceAccount": "fis-sa",
        "duration": "PT3M",
        "percent": "90",
        "workers": "1"
      },
      "targets": {
        "Pods": "serverPods"
      }
    }
  },
  "stopConditions": [{"source": "none"}],
  "roleArn": "arn:aws:iam::181160818749:role/awsfis-demo-prashant"
}
```

*Note:* In an AWS EKS environment, this template is submitted via `aws fis create-experiment-template` and triggered via `aws fis start-experiment`. In local Minikube, we execute the local chaos simulations below.

---

### 9.2 Scenario 2: CrashLoopBackOff Pod Detection & Auto-Recovery

Deploy a faulty service workload that immediately crashes to enter `CrashLoopBackOff`:

```bash
cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: chaos-crashloop-test
  namespace: default
  labels:
    app: chaos-crashloop-test
spec:
  replicas: 1
  selector:
    matchLabels:
      app: chaos-crashloop-test
  template:
    metadata:
      labels:
        app: chaos-crashloop-test
    spec:
      containers:
      - name: failing-container
        image: busybox:1.36
        command: ["/bin/sh", "-c", "echo 'Fatal failure injected'; exit 1"]
EOF
```

Watch the pod enter `CrashLoopBackOff`:

```bash
kubectl get pods -n default -l app=chaos-crashloop-test -w
```

Within 15–30 seconds, observe the health-checker detecting the state, deleting the pod, and recording the audit log:

```bash
kubectl logs -n default -l component=health-checker --tail=15
```

Expected log:
```text
INFO:healer:Self-healing action: {'timestamp': '...', 'pod': 'chaos-crashloop-test-...', 'namespace': 'default', 'action': 'restart_deployment_pod', 'reason': 'CrashLoopBackOff', 'result': 'success', ...}
```

Check the `/api/healing-log` endpoint:

```bash
curl -s http://localhost:8000/api/healing-log | python3 -m json.tool
```

Expected output:
```json
{
    "healing_log": [
        {
            "action": "restart_deployment_pod",
            "details": "Container 'failing-container' in CrashLoopBackOff. Deleted pod to let ReplicaSet reschedule.",
            "namespace": "default",
            "pod": "chaos-crashloop-test-7c87c95b68-xk9vl",
            "reason": "CrashLoopBackOff",
            "result": "success",
            "timestamp": "2026-10-11T14:15:30.123456+00:00"
        }
    ]
}
```

Clean up the test deployment:
```bash
kubectl delete deployment chaos-crashloop-test -n default
```

### Screenshot — CrashLoopBackOff Detection & Auto-Recovery

> showing `kubectl get pods` with the crashlooping pod and health-checker logs recording the auto-recovery._
<img width="1932" height="830" alt="image" src="https://github.com/user-attachments/assets/e4d597e6-ea95-4a26-979e-102182800a6f" />
<img width="3254" height="1340" alt="image" src="https://github.com/user-attachments/assets/dc25769d-892d-49d7-b549-edf6fae72d49" />

---

### 9.3 Scenario 3: Evicted Pod Automated Cleanup

Simulate an Evicted pod in the cluster:

```bash
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: evicted-simulation-pod
  namespace: default
status:
  phase: Failed
  reason: Evicted
  message: "The node was low on resource: ephemeral-storage. Threshold quantity: 100Mi, available: 50Mi."
EOF
```

Verify the pod is present in `Evicted` status:

```bash
kubectl get pod evicted-simulation-pod -n default
# Expected: STATUS: Evicted
```

Wait ~15 seconds for the next health-checker poll cycle, then verify the pod was automatically purged:

```bash
kubectl get pod evicted-simulation-pod -n default
# Expected: Error from server (NotFound): pods "evicted-simulation-pod" not found
```

Check `/api/healing-log`:

```bash
curl -s http://localhost:8000/api/healing-log | python3 -m json.tool | head -30
```

Expected output:
```json
{
    "action": "cleanup_evicted_pod",
    "details": "Pod evicted: The node was low on resource: ephemeral-storage.",
    "namespace": "default",
    "pod": "evicted-simulation-pod",
    "reason": "Evicted",
    "result": "success"
}
```

### Screenshot — Evicted Pod Automated Cleanup

> `kubectl get pod` showing Evicted status followed by automated deletion and the `/api/healing-log` entry._
<img width="1840" height="694" alt="image" src="https://github.com/user-attachments/assets/8f9dbeec-5245-4d15-9c1d-151256fd104c" />
<img width="2646" height="1968" alt="image" src="https://github.com/user-attachments/assets/89dcec71-b4ae-4ba6-b417-357e78b4fe1b" />
---

### 9.4 Scenario 4: CPU Stress Simulation on `server-deployment` (matching AWS FIS)

As defined in `fis-template.json`, FIS targets `server-deployment` with a 90% CPU load for 3 minutes.
To simulate this locally without disrupting application code, run a stress injector container inside the cluster targeting `server-deployment`:

```bash
kubectl run fis-cpu-stress --image=polinux/stress -n default --restart=Never -- \
  stress --cpu 2 --timeout 60s
```

Verify stress container is running:
```bash
kubectl get pod fis-cpu-stress -n default
```

Check GratitudeApp node & pod metrics on Grafana dashboard (`http://localhost:3000`):
- Notice node CPU utilization increase.
- If pods exceed resource limits or fail liveness/readiness probes, health-checker steps in automatically.

Clean up stress pod:
```bash
kubectl delete pod fis-cpu-stress -n default --ignore-not-found
```

### Screenshot — Local Chaos Stress Simulation

> `fis-cpu-stress` running and Grafana metrics reflecting the CPU load._
<img width="2852" height="354" alt="image" src="https://github.com/user-attachments/assets/3e9ff710-91ca-4b7e-920e-bbff99d959e7" />

---

## 10. Verify Audit Logging & Prometheus Metrics

### 10.1 Structured Audit Log Output

```bash
curl -s http://localhost:8000/api/healing-log | python3 -m json.tool
```

---

### 10.2 Prometheus Self-Healing Metrics

Query the Prometheus `/metrics` endpoint:

```bash
curl -s http://localhost:8000/metrics | grep "healthchecker_healing_actions_total"
```

Expected output:
```text
healthchecker_healing_actions_total{action="restart_deployment_pod",namespace="default",reason="CrashLoopBackOff",result="success"} 1.0
healthchecker_healing_actions_total{action="cleanup_evicted_pod",namespace="default",reason="Evicted",result="success"} 1.0
```

### Screenshot — Prometheus Metrics Endpoint

> `curl http://localhost:8000/metrics` displaying the `healthchecker_healing_actions_total` counter._
<img width="2826" height="320" alt="image" src="https://github.com/user-attachments/assets/cda42f3f-151e-415f-9a51-d11e4c8531f5" />
---

## 11. Step-by-Step Screenshot Guide

Summary of the screenshots to capture for Sprint 3:

| # | Suggested Filename | What to Capture |
|---|--------------------|-----------------|
| 1 | `sprint3-fis-rbac.png` | Terminal showing application of FIS RBAC manifests (`rbac.yml`, `fis-sa-cluster-admin.yml`) |
| 2 | `sprint3-healthchecker-running.png` | Terminal showing `kubectl rollout status` and pod logs for `health-checker:sprint3` |
| 3 | `sprint3-crashloop-healing.png` | Pod in `CrashLoopBackOff` being detected and deleted by the health-checker |
| 4 | `sprint3-evicted-cleanup.png` | Evicted simulation pod automatically cleaned up by `scan_and_heal` |
| 5 | `sprint3-chaos-stress.png` | Execution of CPU stress simulation matching `fis-template.json` |
| 6 | `sprint3-healing-log-api.png` | Browser or curl output of `GET /api/healing-log` showing structured audit events |
| 7 | `sprint3-metrics-healing.png` | Terminal output of `/metrics` showing `healthchecker_healing_actions_total` counters |

---

## 12. Sprint 3 Deliverables Checklist

### Code Implementation
- [x] [`healer.py`](k8s-health-checker/healthchecker-app/healer.py) — Self-healing engine with `diagnose_pod()`, `scan_and_heal()`, and audit log buffer
- [x] [`k8s_client.py`](k8s-health-checker/healthchecker-app/k8s_client.py) — Added `delete_pod()` helper
- [x] [`monitor.py`](k8s-health-checker/healthchecker-app/monitor.py) — Poller integrates automated `scan_and_heal()`
- [x] [`main.py`](k8s-health-checker/healthchecker-app/main.py) — Exposes `GET /api/healing-log` and `POST /api/heal`
- [x] [`deployment.yaml`](k8s-health-checker/deploy/healthchecker/deployment.yaml) — Updated image to `health-checker:sprint3` with `ENABLE_SELF_HEALING=true`

### Chaos & Recovery Validation
- [x] Applied AWS FIS RBAC manifests (`rbac.yml`, `fis-sa-cluster-admin.yml`, `fis-experiement-cluster-admin.yml`)
- [x] Evaluated AWS FIS experiment template (`fis-template.json`) targeting `server-deployment`
- [x] Validated auto-recovery of `CrashLoopBackOff` deployment pods
- [x] Validated automated purge of `Evicted` pods
- [x] Verified structured audit log format at `/api/healing-log`
- [x] Verified Prometheus counter `healthchecker_healing_actions_total`
