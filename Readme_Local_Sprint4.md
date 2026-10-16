# Sprint 4 — Advanced Self-Healing (Node Scaling & Resource Balancing): Step-by-Step Guide

**Goal:** Ensure the system can scale and balance resources automatically, optimizing cluster performance and cost. This sprint implements Kubernetes Cluster Autoscaler integration for AWS EKS, Horizontal Pod Autoscalers (HPA) for higher-traffic services, cross-node resource balancing logic and topology spread constraints, and load testing to validate scale-out and scale-in events.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [What's New in Sprint 4](#2-whats-new-in-sprint-4)
3. [Architecture: Autoscaling & Resource Balancing](#3-architecture-autoscaling--resource-balancing)
4. [Step 1: Configure Resource Requests & Limits on Workloads](#4-step-1-configure-resource-requests--limits-on-workloads)
5. [Step 2: Deploy Horizontal Pod Autoscalers (HPA)](#5-step-2-deploy-horizontal-pod-autoscalers-hpa)
6. [Step 3: Cluster Autoscaler Setup for AWS EKS](#6-step-3-cluster-autoscaler-setup-for-aws-eks)
7. [Step 4: Resource Balancing Module & Endpoint](#7-step-4-resource-balancing-module--endpoint)
8. [Step 5: Build & Deploy Health-Checker (`sprint4`)](#8-step-5-build--deploy-health-checker-sprint4)
9. [Step 6: Verify Resource Balancing & Metrics](#9-step-6-verify-resource-balancing--metrics)
10. [Step 7: Execute Load Testing (HPA Scale-Out & Scale-In)](#10-step-7-execute-load-testing-hpa-scale-out--scale-in)
11. [Step-by-Step Screenshot Guide](#11-step-by-step-screenshot-guide)
12. [Sprint 4 Deliverables Checklist](#12-sprint-4-deliverables-checklist)

---

## 1. Prerequisites

Before starting Sprint 4, verify that your cluster has `metrics-server` enabled and the GratitudeApp services running:

```bash
# 1. Verify Minikube status
minikube status

# 2. Verify metrics-server is active
kubectl top nodes
kubectl top pods -n default
# Expected: Live CPU and memory usage displayed for nodes and pods

# If metrics-server is not enabled in Minikube:
# minikube addons enable metrics-server
```

---

## 2. What's New in Sprint 4

| Feature | Description | File / Implementation |
|---------|-------------|-----------------------|
| **Horizontal Pod Autoscaling (HPA)** | Automatically scales `client` (1–5 replicas), `api-gateway` (1–5 replicas), and `server` (1–4 replicas) when average CPU exceeds 50% | `k8s-health-checker/deploy/autoscaling/hpa-gratitudeapp.yaml` |
| **Resource Requests & Limits** | Added CPU and Memory requests/limits to all GratitudeApp deployments so HPA and the scheduler can accurately calculate utilization | `k8s-health-checker/gratitude-k8s/*-deployment.yml` |
| **Topology Spread Constraints** | Spreads replicas across worker nodes (`topologyKey: kubernetes.io/hostname`) to prevent stacking and maintain high availability | `*-deployment.yml` |
| **Cluster Autoscaler on EKS** | Configured Cluster Autoscaler deployment and RBAC targeting the `default-ng` AutoScalingGroup (min 1 / max 3 nodes as defined in `cluster.yaml`) | `k8s-health-checker/deploy/autoscaling/cluster-autoscaler.yaml` |
| **Node Resource Balancing Module** | Health-checker inspects node pod allocation, allocatable CPU/RAM, and emits cluster balance score | `healthchecker-app/balancer.py` |
| **Node Balancing API** | New endpoint `GET /api/node-balancing` returning per-node pod counts, capacity, and distribution report | `healthchecker-app/main.py` |
| **Synthetic Load Generator** | Multi-threaded HTTP traffic generator hitting client and api-gateway endpoints to trigger real-time HPA scale-out | `k8s-health-checker/deploy/autoscaling/load-generator.yaml` |

---

## 3. Architecture: Autoscaling & Resource Balancing

```
                      ┌─────────────────────────────────────────┐
                      │    Synthetic Load Generator (Traffic)   │
                      └────────────────────┬────────────────────┘
                                           │ HTTP requests
                                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ GratitudeApp Cluster                                                                   │
│                                                                                        │
│   ┌──────────────────────────┐      CPU > 50%       ┌──────────────────────────────┐   │
│   │   Metrics Server         │ ───────────────────► │ Horizontal Pod Autoscaler    │   │
│   │   (Scrapes Pod CPU)      │                      │ (api-gateway, client, server)│   │
│   └──────────────────────────┘                      └──────────────┬───────────────┘   │
│                                                                    │ Scales replicas   │
│                                                                    ▼                   │
│                        ┌────────────────────────────────────────────────────────┐      │
│                        │ Replicas scale: 1 ──► 2 ──► 3 ──► 4 (Scale-Out)       │      │
│                        │ When load stops: 4 ──► 2 ──► 1       (Scale-In)       │      │
│                        └───────────────────────────┬────────────────────────────┘      │
│                                                    │                                   │
│                        ┌───────────────────────────┴────────────────────────────┐      │
│                        │ TopologySpreadConstraints & Anti-Affinity               │      │
│                        │ Distributes replicas evenly across worker nodes        │      │
│                        └────────────────────────────────────────────────────────┘      │
│                                                                                        │
│   ┌──────────────────────────┐                     ┌───────────────────────────────┐   │
│   │ Node Group Scale (EKS)   │                     │ Health-Checker Auto-Balancer  │   │
│   │ Cluster Autoscaler       │                     │ GET /api/node-balancing       │   │
│   │ ASG: min 1 / max 3 nodes │                     │ healthchecker_node_pod_count  │   │
│   └──────────────────────────┘                     └───────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Step 1: Configure Resource Requests & Limits on Workloads

For Kubernetes HPA to calculate target CPU percentages (`targetCPUUtilizationPercentage: 50`), pods **must** declare CPU requests.

The manifests in `k8s-health-checker/gratitude-k8s/` have been updated with CPU requests, limits, and `topologySpreadConstraints`:
- **`api-gateway-deployment`**: requests: 50m CPU, 64Mi RAM; limits: 250m CPU, 128Mi RAM
- **`client-deployment`**: requests: 25m CPU, 32Mi RAM; limits: 150m CPU, 128Mi RAM
- **`server-deployment`**: requests: 50m CPU, 64Mi RAM; limits: 250m CPU, 128Mi RAM

Apply the updated manifests to your cluster:

```bash
kubectl apply -f k8s-health-checker/gratitude-k8s/api-gateway-deployment.yml
kubectl apply -f k8s-health-checker/gratitude-k8s/client-deployment.yml
kubectl apply -f k8s-health-checker/gratitude-k8s/server-deployment.yml
```

Verify rollout:

```bash
kubectl rollout status deployment/api-gateway-deployment -n default
kubectl rollout status deployment/client-deployment -n default
kubectl rollout status deployment/server-deployment -n default
```

Verify that `kubectl top pods -n default` continues reporting metrics:

```bash
kubectl top pods -n default
```

---

## 5. Step 2: Deploy Horizontal Pod Autoscalers (HPA)

**File:** [`k8s-health-checker/deploy/autoscaling/hpa-gratitudeapp.yaml`](k8s-health-checker/deploy/autoscaling/hpa-gratitudeapp.yaml)

Apply the HPA definitions:

```bash
kubectl apply -f k8s-health-checker/deploy/autoscaling/hpa-gratitudeapp.yaml
```

Check the status of the HPAs:

```bash
kubectl get hpa -n default
```

Expected output:
```text
NAME              REFERENCE                            TARGETS   MINPODS   MAXPODS   REPLICAS   AGE
api-gateway-hpa   Deployment/api-gateway-deployment    1%/50%    1         5         1          30s
client-hpa        Deployment/client-deployment         2%/50%    1         5         1          30s
server-hpa        Deployment/server-deployment         1%/50%    1         4         1          30s
```

*(Note: If TARGETS initially shows `<unknown>/50%`, wait 15–30 seconds for metrics-server to complete its next scrape cycle).*

### Screenshot — HPA Configured & Active

> `kubectl get hpa -n default` showing all 3 HPAs reporting valid CPU utilization percentages against their 50% target._
<img width="2304" height="486" alt="image" src="https://github.com/user-attachments/assets/311db9b2-8067-4bb1-bc4e-46038c004c55" />


---

## 6. Step 3: Cluster Autoscaler Setup for AWS EKS

**File:** [`k8s-health-checker/deploy/autoscaling/cluster-autoscaler.yaml`](k8s-health-checker/deploy/autoscaling/cluster-autoscaler.yaml)

In AWS EKS production, the worker node group capacity is governed by an AWS AutoScalingGroup (`minSize: 1`, `maxSize: 3`, `desiredCapacity: 2` in `cluster.yaml`).

The manifest includes:
1. `ServiceAccount` `cluster-autoscaler` in `kube-system` with AWS IAM OIDC annotations (`eks.amazonaws.com/role-arn`).
2. RBAC `ClusterRole` and `ClusterRoleBinding` granting full autoscaling permissions.
3. Deployment of `registry.k8s.io/autoscaling/cluster-autoscaler:v1.30.0` configured with auto-discovery tags matching `cluster.yaml`:
   - `--node-group-auto-discovery=asg:tag=k8s.io/cluster-autoscaler/enabled,k8s.io/cluster-autoscaler/gratitude-health-cluster`
   - `--scale-down-utilization-threshold=0.5`
   - `--balance-similar-node-groups`

To validate the manifest syntax:

```bash
kubectl apply --dry-run=client -f k8s-health-checker/deploy/autoscaling/cluster-autoscaler.yaml
```

Expected output:
```text
serviceaccount/cluster-autoscaler created (dry run)
clusterrole.rbac.authorization.k8s.io/cluster-autoscaler created (dry run)
clusterrolebinding.rbac.authorization.k8s.io/cluster-autoscaler created (dry run)
deployment.apps/cluster-autoscaler created (dry run)
```

### Screenshot — Cluster Autoscaler Manifest Validation

> showing `kubectl apply --dry-run=client` of `cluster-autoscaler.yaml` and the `cluster.yaml` node group configuration._
<img width="2586" height="210" alt="image" src="https://github.com/user-attachments/assets/1780dcd6-f93e-489e-952f-1db6d3c91901" />

---

## 7. Step 4: Resource Balancing Module & Endpoint

**File:** [`k8s-health-checker/healthchecker-app/balancer.py`](k8s-health-checker/healthchecker-app/balancer.py)

The new balancer module:
1. Gathers all cluster nodes, their `Ready` status, allocatable CPU, and allocatable memory.
2. Tracks how many pods and replicas of each deployment are scheduled on each node.
3. Calculates a `cluster_balance_ratio` (min/max pod ratio across nodes; 1.0 = balanced).
4. Exposes new Prometheus gauges:
   - `healthchecker_node_pod_count{node="..."}`
   - `healthchecker_node_cpu_capacity_cores{node="..."}`
   - `healthchecker_cluster_balance_ratio`
5. Serves `GET /api/node-balancing`.

---

## 8. Step 5: Build & Deploy Health-Checker (`sprint4`)

Build the updated image inside Minikube:

```bash
minikube image build -t health-checker:sprint4 k8s-health-checker/healthchecker-app/
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

---

## 9. Step 6: Verify Resource Balancing & Metrics

Start port-forwarding the health-checker:

```bash
kubectl port-forward svc/health-checker-cluster-ip-service 8000:8000 -n default
```

### 9.1 Test `/api/node-balancing`

```bash
curl -s http://localhost:8000/api/node-balancing | python3 -m json.tool
```

Expected output:
```json
{
    "cluster_balance_ratio": 1.0,
    "node_count": 1,
    "nodes": [
        {
            "cpu_allocatable": "8",
            "memory_allocatable": "32870104Ki",
            "name": "minikube",
            "pod_count": 11,
            "ready": "True"
        }
    ],
    "status": "balanced",
    "total_pods_in_namespace": 11,
    "workload_distribution": {
        "api-gateway-deployment": {
            "minikube": 1
        },
        "client-deployment": {
            "minikube": 1
        },
        "server-deployment": {
            "minikube": 1
        }
    }
}
```

### Screenshot — `/api/node-balancing` Response

<img width="1218" height="1774" alt="image" src="https://github.com/user-attachments/assets/54d67962-f10c-4fd0-9783-a14f030f2e39" />


---

### 9.2 Test Prometheus Metrics for Resource Balancing

```bash
curl -s http://localhost:8000/metrics | grep -E "healthchecker_node_pod_count|healthchecker_cluster_balance_ratio"
```

Expected output:
```text
# HELP healthchecker_node_pod_count Number of pods scheduled on a specific node
# TYPE healthchecker_node_pod_count gauge
healthchecker_node_pod_count{node="minikube"} 11.0
# HELP healthchecker_cluster_balance_ratio Ratio of min/max pod count across nodes (1.0 = perfect balance)
# TYPE healthchecker_cluster_balance_ratio gauge
healthchecker_cluster_balance_ratio 1.0
```

---

## 10. Step 7: Execute Load Testing (HPA Scale-Out & Scale-In)

**File:** [`k8s-health-checker/deploy/autoscaling/load-generator.yaml`](k8s-health-checker/deploy/autoscaling/load-generator.yaml)

### 10.1 Trigger Load Generation (Scale-Out)

Deploy the synthetic traffic generator:

```bash
kubectl apply -f k8s-health-checker/deploy/autoscaling/load-generator.yaml
kubectl rollout status deployment/load-generator -n default
```

Watch the HPA and pod replicas respond to increased CPU load:

```bash
kubectl get hpa -n default -w
```

Watch in another terminal as pods scale out:

```bash
kubectl get pods -n default -l component=api-gateway
kubectl get pods -n default -l component=web
```

Within 30–60 seconds, CPU utilization surpasses the 50% target threshold:
- `client-deployment` scales from 1 replica to 2, 3, or more replicas.
- `api-gateway-deployment` scales from 1 replica to 2, 3, or more replicas.

### Screenshot — HPA Scale-Out Under Load

> showing `kubectl get hpa` and `kubectl get pods` with replicas scaled up (e.g. 3/5 replicas) under load._
<img width="2172" height="516" alt="image" src="https://github.com/user-attachments/assets/3ac256f9-91f2-465f-8b2a-6dc623540d8f" />

---

### 10.2 Stop Load Generation (Scale-In)

Delete the load generator:

```bash
kubectl delete -f k8s-health-checker/deploy/autoscaling/load-generator.yaml
```

Watch the HPA stabilize and scale pods back down:

```bash
kubectl get hpa -n default -w
```

After the 60-second stabilization window, CPU drops below 5%, and HPA scales the deployments back to `1` replica:

```bash
kubectl get pods -n default -l component=api-gateway
kubectl get pods -n default -l component=web
# Expected: Exactly 1 replica running per service
```

### Screenshot — HPA Scale-In After Load Stops

> showing `kubectl get hpa` and `kubectl get pods` returning back to 1 replica after the load test completes._
<img width="2204" height="80" alt="image" src="https://github.com/user-attachments/assets/c5ad7ac6-ca59-4839-a912-17efe0f270a6" />
<img width="1830" height="228" alt="image" src="https://github.com/user-attachments/assets/d4c2be89-523c-4090-93cd-c2f80cb4f532" />

---

## 11. Sprint 4 Deliverables Checklist

### Autoscaling & Scaling Policies
- [x] Defined HorizontalPodAutoscalers for `api-gateway`, `client`, and `server` in [`hpa-gratitudeapp.yaml`](k8s-health-checker/deploy/autoscaling/hpa-gratitudeapp.yaml)
- [x] Configured CPU & RAM resource requests and limits across GratitudeApp deployment manifests
- [x] Configured `topologySpreadConstraints` to balance replicas across worker nodes
- [x] Configured AWS EKS Cluster Autoscaler manifest & RBAC in [`cluster-autoscaler.yaml`](k8s-health-checker/deploy/autoscaling/cluster-autoscaler.yaml) matching `cluster.yaml`

### Health-Checker Module & Metrics
- [x] Implemented [`balancer.py`](k8s-health-checker/healthchecker-app/balancer.py) with node allocation and balance score
- [x] Added `GET /api/node-balancing` endpoint to [`main.py`](k8s-health-checker/healthchecker-app/main.py)
- [x] Added Prometheus metrics: `healthchecker_node_pod_count`, `healthchecker_node_cpu_capacity_cores`, `healthchecker_cluster_balance_ratio`
- [x] Integrated balancer report into poller thread in [`monitor.py`](k8s-health-checker/healthchecker-app/monitor.py)

### Validation & Load Testing
- [x] Created synthetic load generator in [`load-generator.yaml`](k8s-health-checker/deploy/autoscaling/load-generator.yaml)
- [x] Validated HPA automatic scale-out under elevated CPU traffic
- [x] Validated HPA automatic scale-in after load termination
