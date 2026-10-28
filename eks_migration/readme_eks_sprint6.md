# Sprint 6 — Grafana Dashboard and Final EKS Verification

This guide applies the Sprint 6 observability dashboard to the existing EKS
monitoring stack, reviews project documentation, and performs optional,
controlled end-to-end checks. It does **not** recreate or delete the EKS
cluster.

> **Production safety:** The checks that generate traffic, create failing
> pods, change replicas, or send notifications are optional. Run them only in
> a non-production environment or during an approved window. Stop load
> generators and restore any changed replica counts when finished.

## Contents

1. [Prerequisites](#1-prerequisites)
2. [Sprint 6 components](#2-sprint-6-components)
3. [Apply and verify the dashboard](#3-apply-and-verify-the-dashboard)
4. [Open the Grafana dashboard](#4-open-the-grafana-dashboard)
5. [Review project documentation](#5-review-project-documentation)
6. [Final end-to-end checks](#6-final-end-to-end-checks)
7. [Safe cleanup](#7-safe-cleanup)
8. [Checklist](#8-checklist)

## 1. Prerequisites

Run commands in **Ubuntu/WSL** from the repository root:

```bash
cd /mnt/c/Users/CBhalla/Desktop/herovired/capstone_eks/Capstone_Project_HeroVired
aws eks update-kubeconfig --region us-east-1 --name gratitude-health-cluster
kubectl get nodes
kubectl get pods -n default
kubectl get pods -n monitoring
```

Confirm the expected EKS cluster is the current context, nodes are `Ready`,
and the GratitudeApp, health-checker, Prometheus, Grafana, and Alertmanager
pods are healthy. Confirm Metrics Server/HPA if Sprint 4 checks are planned:

```bash
kubectl top nodes
kubectl get hpa -n default
```


This guide assumes the Grafana service is `monitoring-grafana`. Use
`kubectl get svc -n monitoring` to confirm its name and port.

## 2. Sprint 6 components

| Component | Project location |
|---|---|
| Full observability dashboard ConfigMap | `k8s-health-checker/deploy/grafana/sprint6-full-dashboard.yaml` |
| User guide | `docs/user-guide.md` |
| Alerting guide | `docs/alerting-and-notifications.md` |
| Grafana dashboard UID | `gratitude-s6-v1` |

The ConfigMap is labeled `grafana_dashboard: "1"` for the Grafana dashboard
sidecar. Dashboard panels query health-checker metrics, Kubernetes metrics,
and Prometheus alerts. Panels with no data usually indicate that the
corresponding metric is not being scraped or has not yet been emitted.

## 3. Apply and verify the dashboard

Apply the dashboard ConfigMap to the existing monitoring namespace:

```bash
kubectl apply -f k8s-health-checker/deploy/grafana/sprint6-full-dashboard.yaml
kubectl get configmap sprint6-full-dashboard -n monitoring
```

Wait about 30 seconds for the dashboard sidecar to discover the ConfigMap.
Verify the health-checker and its metrics endpoint:

```bash
kubectl get pods -n default -l component=health-checker
```

Start a port-forward in one WSL terminal:

```bash
kubectl port-forward -n default svc/health-checker-cluster-ip-service 8000:8000
```

From another terminal, check health and metrics:

```bash
curl -s http://localhost:8000/healthz
curl -s http://localhost:8000/metrics | grep healthchecker_ | head -10
```

Check that the ConfigMap has the dashboard label and the Grafana sidecar is
running:

```bash
kubectl get configmap sprint6-full-dashboard -n monitoring \
  -o jsonpath='{.metadata.labels.grafana_dashboard}'; echo
kubectl get pods -n monitoring -o wide
```

If the dashboard does not appear, inspect the Grafana and sidecar logs:

```bash
GRAFANA_POD=$(kubectl get pod -n monitoring -l app.kubernetes.io/name=grafana \
  -o jsonpath='{.items[0].metadata.name}')
kubectl logs -n monitoring "$GRAFANA_POD" -c grafana-sc-dashboard --tail=50
kubectl logs -n monitoring "$GRAFANA_POD" -c grafana --tail=50
```

If the sidecar container name or selector differs, get the pod's actual
containers and use those names. Do not restart or upgrade the monitoring
release merely because the dashboard has not appeared; first inspect sidecar
logs, labels, ConfigMap contents, and Prometheus data.

## 4. Open the Grafana dashboard

Port-forward Grafana from WSL. Keep this terminal open:

```bash
kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80
```

Open **http://localhost:3000** in a browser on the same machine. Use the
configured Grafana credentials; do not assume a default password. The EKS
Helm values in this project may set a demo password, so change it for any
shared or persistent environment.

In Grafana, open **Dashboards → Browse** and select **GratitudeApp — Full
Observability Dashboard (Sprint 6)**. The dashboard includes node readiness,
cluster balance, deployment health, pod readiness/restarts, HPA replicas,
CPU capacity, active alerts, and historical balance.

Allow Prometheus to collect data before interpreting charts. A healthy panel
may be empty when its metric has not yet been emitted; verify the metric in
`/metrics` and Prometheus targets before treating no data as an application
failure.

## 5. Review project documentation

Review the EKS setup and runtime behavior in:

- `docs/user-guide.md` — API, metrics, configuration, troubleshooting, and
  overall architecture. Its Minikube-specific commands describe local usage;
  use the EKS commands in this guide for the AWS cluster.
- `docs/alerting-and-notifications.md` — mock/live Slack modes and alert
  routing. Do not put real webhook credentials in repository files.
- `readme_eks_sprint2.md` through `readme_eks_sprint5.md` — prior sprint EKS
  runbooks.

## 6. Final end-to-end checks

### 6.1 Verify the application and monitoring stack

```bash
kubectl get deployments -n default
kubectl get pods -n default
kubectl get pods -n monitoring
kubectl get hpa -n default
kubectl get nodes
```

Check the public GratitudeApp ingress/load balancer endpoint using the
existing Sprint 1–3 EKS instructions. Do not create a new public LoadBalancer
or expose Grafana/Prometheus publicly for this verification.

### 6.2 Optional: test health-checker API

With the health-checker port-forward from Step 3 open:

```bash
curl -s http://localhost:8000/api/summary | python3 -m json.tool
curl -s http://localhost:8000/api/node-balancing | python3 -m json.tool
curl -s http://localhost:8000/metrics | grep healthchecker_ | head -10
```

### 6.3 Optional: test HPA and dashboard panels

Only if a temporary load test is approved, apply the Sprint 4 load generator:

```bash
kubectl apply -f k8s-health-checker/deploy/autoscaling/load-generator.yaml
kubectl get hpa -n default -w
```

Observe the HPA/Grafana panels briefly, then stop traffic immediately:

```bash
kubectl delete -f k8s-health-checker/deploy/autoscaling/load-generator.yaml --ignore-not-found
```

Leave the HPA resources in place and wait for them to settle at minimum
replicas. Do not test scale-out on production or assume node capacity is
unlimited.

### 6.4 Optional: verify a Prometheus alert

If the `GratitudeAppDeploymentDegraded` rule is installed, a controlled test
can scale a non-HPA-managed deployment such as `entries-deployment` to zero.
Record the current replica count first and do this only in a safe test window:

```bash
ORIGINAL_REPLICAS=$(kubectl get deployment entries-deployment -n default \
  -o jsonpath='{.spec.replicas}')
echo "Recorded replicas: $ORIGINAL_REPLICAS"
kubectl scale deployment entries-deployment --replicas=0 -n default
```

After the alert evaluation period, inspect Prometheus at
`http://localhost:9090/alerts` using a local port-forward:

```bash
kubectl port-forward -n monitoring svc/monitoring-kube-prometheus-prometheus 9090:9090
```

Restore the previously recorded replica count immediately after the
verification from the same terminal:

```bash
kubectl scale deployment entries-deployment --replicas="$ORIGINAL_REPLICAS" -n default
kubectl rollout status deployment/entries-deployment -n default
```

Skip this check if the deployment is serving users, already unhealthy, or
HPA-managed. Verify the dashboard and alert rules without forcing a failure
when changing replicas is not safe.

### 6.5 Optional: verify Sprint 5 notification

If Sprint 5 is deployed, use its port-forward and test endpoint:

```bash
curl -s -X POST http://localhost:8000/api/notify/slack \
  -H 'Content-Type: application/json' \
  -d '{"title":"Sprint 6 EKS verification","message":"Notification test","severity":"info"}' \
  | python3 -m json.tool
```

An empty webhook URL results in a simulated/mock notification. For live
delivery, verify the Secret-backed configuration without printing its value.

## 7. Safe cleanup

Stop any active port-forward with **Ctrl+C** in its terminal. Ensure test
traffic and test workloads are removed:

```bash
kubectl delete deployment load-generator -n default --ignore-not-found
kubectl delete deployment test-healing-notifier -n default --ignore-not-found
kubectl get pods -n default
kubectl get hpa -n default
```

Restore any deployment replica counts changed during optional alert testing.
The dashboard ConfigMap is safe to leave installed. If you intentionally want
to remove only the Sprint 6 dashboard:

```bash
kubectl delete -f k8s-health-checker/deploy/grafana/sprint6-full-dashboard.yaml
```

Do **not** run the local Minikube teardown script for this EKS task. Do not
delete the EKS cluster, node group, VPC, persistent volumes, or monitoring
release as part of Sprint 6 verification. Full AWS cleanup is a separate,
destructive operation that can remove application data and should be done
only after reviewing all dependent resources and confirming the target
cluster.

## 8. Checklist

- [ ] EKS context, nodes, application, and monitoring pods are healthy.
- [ ] Sprint 6 dashboard ConfigMap exists in `monitoring` with its dashboard
      label.
- [ ] Grafana dashboard appears and expected Prometheus metrics are present.
- [ ] User/alerting documentation has been reviewed for EKS-specific steps.
- [ ] Optional tests were run only in a safe window; load generator was
      deleted and changed replica counts restored.
- [ ] No local Minikube teardown or EKS cluster deletion was performed.
