# Sprint 2 — Health Monitoring on Amazon EKS

This guide deploys the Sprint 2 health-checker changes, Grafana dashboard, and
Prometheus alert rules to the existing GratitudeApp EKS cluster. It builds and
pushes the health-checker image to Amazon ECR; it does not use Minikube.

> **AWS costs:** The EKS cluster, EC2 nodes, EBS volumes, NAT gateway, and
> load balancers can incur charges while running. The monitoring stack also
> consumes node resources. Delete resources when they are no longer needed.

## Contents

1. [Prerequisites](#1-prerequisites)
   - [Step-by-step WSL deployment runbook](#step-by-step-wsl-deployment-runbook)
2. [Sprint 2 changes](#2-sprint-2-changes)
3. [Verify the EKS connection](#3-verify-the-eks-connection)
4. [Build and push the updated health-checker image](#4-build-and-push-the-updated-health-checker-image)
5. [Deploy the health-checker and monitoring stack](#5-deploy-the-health-checker-and-monitoring-stack)
6. [Install the Grafana dashboard and alert rules](#6-install-the-grafana-dashboard-and-alert-rules)
7. [Verify the deployment](#7-verify-the-deployment)
8. [Open Grafana and Prometheus](#8-open-grafana-and-prometheus)
9. [Test and restore an alert](#9-test-and-restore-an-alert)
10. [Troubleshooting](#10-troubleshooting)
11. [Sprint 2 checklist](#11-sprint-2-checklist)

## 1. Prerequisites

Run the commands in this guide from **Ubuntu/WSL**, in the repository root.
The Sprint 1 EKS cluster and GratitudeApp should already be deployed.

Required tools in WSL:

- AWS CLI, configured for the AWS account that owns the EKS cluster and ECR
- `kubectl`
- Docker, available to WSL and able to build Linux container images
- `curl` and standard shell utilities

Check the tools and AWS identity:

```bash
aws --version
kubectl version --client
docker version
aws sts get-caller-identity
```

### Step-by-step WSL deployment runbook

Follow these steps in order. Run every command in **Ubuntu/WSL**, not at the
PowerShell prompt. If you are currently in PowerShell, enter WSL with:

```powershell
wsl
```

1. Change to the repository root and confirm the expected project is present:

   ```bash
   cd /mnt/c/Users/CBhalla/Desktop/herovired/capstone_eks/Capstone_Project_HeroVired
   pwd
   ls k8s-health-checker
   ```

2. Normalize line endings on the shell scripts used in this deployment. This
   prevents Bash errors such as `$'\r': command not found` when the files were
   saved with Windows CRLF endings:

   ```bash
   sed -i 's/\r$//' \
     k8s-health-checker/scripts/00-build-and-push-healthchecker.sh \
     k8s-health-checker/scripts/03-deploy-monitoring.sh
   ```

3. Confirm AWS identity, configure `kubectl` for the existing EKS cluster, and
   verify node access:

   ```bash
   aws sts get-caller-identity
   aws eks update-kubeconfig --region us-east-1 --name gratitude-health-cluster
   kubectl config current-context
   kubectl get nodes
   ```

   Stop if the AWS account is not the account you intend to use or if the nodes
   are not `Ready`.

4. Confirm the Sprint 1 application and Sprint 2 monitoring pods are healthy:

   ```bash
   kubectl get pods -n default
   kubectl get pods -n monitoring
   ```

5. `k8s_client.py` (sometimes referred to as `client.py`) and `monitor.py` are
   Python source files, not Kubernetes manifests. **Do not run `kubectl apply`
   on them.** Their Sprint 2 implementation is already in
   `k8s-health-checker/healthchecker-app`. Check that the source includes the
   pod-readiness fields and new gauges:

   ```bash
   grep -n 'conditions\|ready' k8s-health-checker/healthchecker-app/k8s_client.py
   grep -n 'POD_READY\|DEPLOYMENT_ALL_AVAILABLE' k8s-health-checker/healthchecker-app/monitor.py
   ```

   If the expected code is not present in your working copy, update the Python
   source first. The deployment step below packages all files in
   `healthchecker-app` into the image.

6. Build the updated health-checker source and push it to ECR:

   ```bash
   bash ./k8s-health-checker/scripts/00-build-and-push-healthchecker.sh
   ```

   Confirm the script reports a successful push and that the ECR URI it prints
   matches the `image:` value in
   `k8s-health-checker/deploy/healthchecker/deployment.yaml`.

7. Apply the Kubernetes Deployment manifest. This applies Kubernetes YAML; it
   does not upload Python source files:

   ```bash
   kubectl apply -f k8s-health-checker/deploy/healthchecker/deployment.yaml
   ```

8. Because the deployment uses the mutable `latest` image tag, restart it so
   EKS pulls the image you just pushed. Wait until the rollout succeeds:

   ```bash
   kubectl rollout restart deployment/health-checker-deployment -n default
   kubectl rollout status deployment/health-checker-deployment -n default --timeout=180s
   kubectl get pods -n default -l component=health-checker
   ```

9. Apply the Sprint 2 Kubernetes resources for Grafana and Prometheus:

   ```bash
   kubectl apply -f k8s-health-checker/deploy/grafana/node-pod-health-dashboard.yaml
   kubectl apply -f k8s-health-checker/deploy/alerts/gratitudeapp-alerts.yaml
   kubectl get configmap node-pod-health-dashboard -n monitoring
   kubectl get prometheusrule gratitudeapp-health-alerts -n monitoring
   ```

10. Check the API and Sprint 2 metrics. Start the port-forward in one WSL
   terminal and leave it running:

   ```bash
   kubectl port-forward -n default svc/health-checker-cluster-ip-service 8000:8000
   ```

   In a second WSL terminal, run:

   ```bash
   curl http://localhost:8000/healthz
   curl -s http://localhost:8000/metrics | grep healthchecker_pod_ready
   curl -s http://localhost:8000/metrics | grep healthchecker_deployment_all_replicas_available
   curl -s http://localhost:8000/api/pods
   ```

   `/api/pods` should include `ready` and `conditions` for each pod.

10. Open Grafana and Prometheus using the port-forward instructions in
    [Section 8](#8-open-grafana-and-prometheus). Confirm the dashboard appears
    and the `health-checker` target is `UP` before optionally testing an alert.

This runbook assumes the monitoring stack from Sprint 1 is already installed.
You do **not** need to rerun the Helm-based monitoring script just to update
`k8s_client.py` or `monitor.py`. If you are provisioning the monitoring stack
for the first time, use the project Helm script separately and verify its Helm
version prerequisite before running it.

## 2. Sprint 2 changes

The health-checker code in `k8s-health-checker/healthchecker-app` provides
additional pod readiness detail and Prometheus metrics:

| Metric | Labels | Meaning |
|---|---|---|
| `healthchecker_pod_ready` | `namespace`, `pod` | `1` when the pod's Ready condition is True; otherwise `0` |
| `healthchecker_deployment_all_replicas_available` | `namespace`, `deployment` | `1` when available replicas are at least the desired replicas; otherwise `0` |
| `healthchecker_node_ready` | `node` | `1` when the node is Ready |
| `healthchecker_pod_restarts_total` | `namespace`, `pod` | Container restart count for the pod |
| `healthchecker_pod_phase_running` | `namespace`, `pod` | `1` when the pod phase is Running |
| `healthchecker_deployment_available_replicas` | `namespace`, `deployment` | Available replica count |
| `healthchecker_deployment_desired_replicas` | `namespace`, `deployment` | Desired replica count |

The `/api/pods` response now includes a boolean `ready` field and a `conditions`
map for each pod. The dashboard and alert resources are:

- `k8s-health-checker/deploy/grafana/node-pod-health-dashboard.yaml`
- `k8s-health-checker/deploy/alerts/gratitudeapp-alerts.yaml`

### What gets applied to EKS?

`k8s_client.py` and `monitor.py` are source code. Docker packages them into the
health-checker image; the image is pushed to ECR, and the Deployment is updated
to run that image. You do not apply `.py` files directly with `kubectl`.

The dashboard ConfigMap and PrometheusRule are Kubernetes resources, so apply
their YAML files with `kubectl apply -f`, as shown in the runbook. The EKS
monitoring stack itself must already be installed for Grafana and Prometheus to
load those resources.

## 3. Verify the EKS connection

Confirm AWS is using the expected account, then set the WSL kubeconfig to the
existing cluster:

```bash
aws sts get-caller-identity
aws eks update-kubeconfig --region us-east-1 --name gratitude-health-cluster
kubectl config current-context
kubectl get nodes
```

The context should identify the EKS cluster and its nodes should be `Ready`.
Check that the GratitudeApp and ingress controller are available:

```bash
kubectl get pods -n default
kubectl get pods -n ingress-nginx
```

## 4. Build and push the updated health-checker image

From the repository root, build the Sprint 2 source and push it to ECR:

```bash
bash ./k8s-health-checker/scripts/00-build-and-push-healthchecker.sh
```

The script uses the AWS account returned by `aws sts get-caller-identity`,
creates the `gratitude-health-checker` ECR repository if necessary, and pushes
the image tagged `latest` to `us-east-1`.

Verify that the image is present:

```bash
aws ecr describe-images \
  --repository-name gratitude-health-checker \
  --region us-east-1 \
  --query 'imageDetails[].imageTags[]'
```

Check `k8s-health-checker/deploy/healthchecker/deployment.yaml`: its `image`
must match the ECR URI printed by the build script. The EKS worker node role
must be allowed to pull images from that ECR repository.

## 5. Deploy the health-checker and monitoring stack

For an existing Sprint 1 EKS cluster with Prometheus and Grafana already
running, apply the health-checker Deployment directly:

```bash
kubectl apply -f k8s-health-checker/deploy/healthchecker/deployment.yaml
```

The RBAC is unchanged for Sprint 2 and should already exist. If this is a new
cluster without the health-checker RBAC, apply it once:

```bash
kubectl apply -f k8s-health-checker/deploy/healthchecker/rbac.yaml
```

Because the image uses the mutable `latest` tag, restart the Deployment after
the image push to ensure the pod pulls the newly built image:

```bash
kubectl rollout restart deployment/health-checker-deployment -n default
kubectl rollout status deployment/health-checker-deployment -n default --timeout=180s
```

If the monitoring stack is not installed, install it separately with the
project's Helm script, which requires Helm 3.x:

```bash
bash ./k8s-health-checker/scripts/03-deploy-monitoring.sh
```

That script applies health-checker resources and installs/upgrades
`kube-prometheus-stack`; the dashboard ConfigMap and PrometheusRule still need
to be applied separately in the next section.

## 6. Install the Grafana dashboard and alert rules

Apply the dashboard ConfigMap and Prometheus alert rules:

```bash
kubectl apply -f k8s-health-checker/deploy/grafana/node-pod-health-dashboard.yaml
kubectl apply -f k8s-health-checker/deploy/alerts/gratitudeapp-alerts.yaml
```

The dashboard ConfigMap is labeled for the Grafana dashboard sidecar to discover
and load it. The PrometheusRule uses `release: monitoring`, matching the Helm
release name.

Verify both resources exist:

```bash
kubectl get configmap -n monitoring node-pod-health-dashboard
kubectl get prometheusrule -n monitoring gratitudeapp-health-alerts
```

The rule file defines:

| Alert | Condition | For | Severity |
|---|---|---:|---|
| `NodeNotReady` | A node readiness metric is `0` | 2 minutes | critical |
| `GratitudeAppDeploymentDegraded` | A listed GratitudeApp deployment has fewer available than desired replicas | 1 minute | warning |
| `PodHighRestartCount` | A default-namespace pod has more than 5 restarts | Immediately | warning |
| `PodNotReady` | A pod is Running but not Ready | 2 minutes | warning |

These rules create Prometheus alerts; notification delivery requires Alertmanager
to be configured with a receiver.

## 7. Verify the deployment

Check pod status:

```bash
kubectl get pods -n default
kubectl get pods -n monitoring
```

The health-checker and monitoring pods should become `Running` and Ready.
The migration job may remain `Completed`.

Check the health-checker API and new metrics. Start this port-forward in one
WSL terminal and leave it running:

```bash
kubectl port-forward -n default svc/health-checker-cluster-ip-service 8000:8000
```

In a second WSL terminal:

```bash
curl http://localhost:8000/healthz
curl -s http://localhost:8000/metrics | grep healthchecker_pod_ready
curl -s http://localhost:8000/metrics | grep healthchecker_deployment_all_replicas_available
curl -s http://localhost:8000/api/pods
curl -s http://localhost:8000/api/summary
```

The health endpoint should return `{"status":"ok"}`. Pod JSON should include
`ready` and `conditions`; the metrics endpoint should return per-pod readiness
and per-deployment availability series.

Check that Prometheus has discovered the health-checker target by opening its
targets page as described below. The `health-checker` target should be `UP`.

## 8. Open Grafana and Prometheus

### Grafana

Start a port-forward in WSL and leave the terminal open:

```bash
kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80
```

Open [http://localhost:3000](http://localhost:3000). The configured username is
`admin`; the current project values file sets the password to `changeme`.
Change this password before using the deployment beyond a temporary project
environment.

Open **Dashboards → Browse → GratitudeApp — Node & Pod Health**. You can also
open **Explore**, select Prometheus, and query:

```promql
healthchecker_pod_ready
```

### Prometheus

In a separate WSL terminal, start the Prometheus port-forward:

```bash
kubectl port-forward -n monitoring svc/monitoring-kube-prometheus-prometheus 9090:9090
```

Open [http://localhost:9090/targets](http://localhost:9090/targets) and confirm
the `health-checker` scrape target is `UP`. Prometheus alert rules can be
inspected at [http://localhost:9090/alerts](http://localhost:9090/alerts).

## 9. Test and restore an alert

This test intentionally degrades the frontend and can make the application
unavailable while it is scaled down. Only do this when a brief interruption is
acceptable.

In another WSL terminal, scale the client Deployment to zero:

```bash
kubectl scale deployment/client-deployment --replicas=0 -n default
```

After the rule's `for` duration and Prometheus evaluation interval, check
`http://localhost:9090/alerts` for `GratitudeAppDeploymentDegraded`. Restore the
Deployment immediately after the test:

```bash
kubectl scale deployment/client-deployment --replicas=1 -n default
kubectl rollout status deployment/client-deployment -n default --timeout=180s
```

The alert should return to inactive after the health metric updates and the
alert's pending state clears.

## 10. Troubleshooting

### Health-checker pod cannot pull its image

```bash
kubectl describe pod -n default -l component=health-checker
kubectl get events -n default --sort-by=.lastTimestamp
```

Confirm the image URI in the Deployment exists in ECR, the image was pushed to
`us-east-1`, and the EKS worker node role can pull from ECR. After pushing a
replacement image with the same tag, restart the Deployment to pull it.

### Health-checker metrics are missing or Prometheus target is down

```bash
kubectl get pods -n default -l component=health-checker
kubectl logs -n default deployment/health-checker-deployment
kubectl get endpoints -n default health-checker-cluster-ip-service
```

Confirm the pod is Ready, the service has an endpoint, and its scrape
annotations remain present in the Deployment.

### Dashboard is not visible

```bash
kubectl get configmap -n monitoring node-pod-health-dashboard -o yaml
kubectl get pods -n monitoring
```

Allow the Grafana sidecar time to load the ConfigMap. Confirm the ConfigMap has
the `grafana_dashboard: "1"` label and Grafana is running.

### Alert rules are not loaded

```bash
kubectl get prometheusrule -n monitoring gratitudeapp-health-alerts -o yaml
```

Confirm the resource has label `release: monitoring`, matching the Helm release,
and that the health-checker metrics exist in Prometheus.

## 11. Sprint 2 checklist

- [ ] EKS kubeconfig points to `gratitude-health-cluster`; nodes are Ready.
- [ ] Sprint 2 health-checker image is pushed to ECR.
- [ ] Health-checker Deployment is using the ECR image and rolled out.
- [ ] Prometheus and Grafana pods are Ready in `monitoring`.
- [ ] Dashboard ConfigMap and PrometheusRule exist in `monitoring`.
- [ ] `/api/pods` returns `ready` and `conditions`.
- [ ] Prometheus exposes `healthchecker_pod_ready` and
      `healthchecker_deployment_all_replicas_available`.
- [ ] Prometheus `health-checker` target is `UP`.
- [ ] Grafana dashboard **GratitudeApp — Node & Pod Health** is visible.
- [ ] Alert rules appear in Prometheus and any test-scaled Deployment has been
      restored.
