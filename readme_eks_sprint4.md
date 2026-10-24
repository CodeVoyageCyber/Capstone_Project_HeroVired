# Sprint 4 — Autoscaling and Resource Balancing on Amazon EKS

This guide applies Sprint 4 resource requests, topology spread settings, HPAs,
health-checker balancing metrics, and an optional EKS Cluster Autoscaler
configuration to the existing GratitudeApp EKS cluster.

> **Cost and availability notice:** HPA load tests increase pod counts and
> CPU use. Cluster Autoscaler may add EC2 worker nodes. Both can increase AWS
> charges. The load-generator manifest continuously sends requests; delete it
> immediately after the test. Do not run load or autoscaling tests on a
> production/shared cluster without approval.

## Contents

1. [Prerequisites](#1-prerequisites)
2. [Sprint 4 components](#2-sprint-4-components)
3. [Step-by-step EKS deployment](#3-step-by-step-eks-deployment)
4. [Verify resource balancing](#4-verify-resource-balancing)
5. [Test HPA scale-out and scale-in](#5-test-hpa-scale-out-and-scale-in)
6. [Optional: configure Cluster Autoscaler for EKS](#6-optional-configure-cluster-autoscaler-for-eks)
7. [Troubleshooting and cleanup](#7-troubleshooting-and-cleanup)
8. [Checklist](#8-checklist)

## 1. Prerequisites

Run commands in **Ubuntu/WSL** from the repository root. Sprint 1–3 should
already be deployed, with healthy GratitudeApp services, health-checker, and
Prometheus/Grafana.

Required tools:

- AWS CLI configured for the account and region that contain the EKS cluster
- `kubectl`, Docker, and `curl`
- ECR push permissions if rebuilding the health-checker image

From PowerShell, enter WSL with `wsl`. In WSL:

```bash
cd /mnt/c/Users/CBhalla/Desktop/herovired/capstone_eks/Capstone_Project_HeroVired
aws sts get-caller-identity
aws eks update-kubeconfig --region us-east-1 --name gratitude-health-cluster
kubectl config current-context
kubectl get nodes
kubectl get pods -n default
kubectl get pods -n monitoring
```

Proceed only when the AWS account is expected, EKS nodes are `Ready`, and the
baseline application/monitoring pods are healthy.

Check that Metrics Server is available; HPA CPU metrics depend on it:

```bash
kubectl top nodes
kubectl top pods -n default
```

If either command reports that the metrics API is unavailable, configure
Metrics Server for this EKS cluster using the AWS-supported add-on or the
upstream Kubernetes deployment appropriate for the cluster version. Avoid
installing a second copy if one already exists. Continue only after `kubectl
top` returns live metrics.

## 2. Sprint 4 components

| Component | Project resource/code |
|---|---|
| CPU/memory requests, limits, and topology spread | `k8s-health-checker/gratitude-k8s/*-deployment.yml` |
| CPU HPAs for client, API gateway, and server | `k8s-health-checker/deploy/autoscaling/hpa-gratitudeapp.yaml` |
| Node/pod balance report and Prometheus metrics | `k8s-health-checker/healthchecker-app/balancer.py` |
| Balance API | `GET /api/node-balancing` |
| Optional EKS node scaling | `k8s-health-checker/deploy/autoscaling/cluster-autoscaler.yaml` |
| Disposable HPA load test | `k8s-health-checker/deploy/autoscaling/load-generator.yaml` |

The Python module is bundled into the health-checker image; it is not applied
directly with `kubectl`. The health-checker must run a build containing
`balancer.py` and the `/api/node-balancing` endpoint.

## 3. Step-by-step EKS deployment

### Step 1: Apply the resource-enabled GratitudeApp Deployments

The EKS manifests define CPU requests and limits for the HPA targets and
topology spread constraints. Apply the three updated workloads:

```bash
kubectl apply -f k8s-health-checker/gratitude-k8s/api-gateway-deployment.yml
kubectl apply -f k8s-health-checker/gratitude-k8s/client-deployment.yml
kubectl apply -f k8s-health-checker/gratitude-k8s/server-deployment.yml
```

Wait for each rollout and ensure there are no pending or failing pods:

```bash
kubectl rollout status deployment/api-gateway-deployment -n default
kubectl rollout status deployment/client-deployment -n default
kubectl rollout status deployment/server-deployment -n default
kubectl get pods -n default
kubectl top pods -n default
```

### Step 2: Apply the Sprint 4 HPAs

The manifest targets 50% average CPU utilization with these ranges:

- `api-gateway-deployment`: 1–5 replicas
- `client-deployment`: 1–5 replicas
- `server-deployment`: 1–4 replicas

Apply and inspect them:

```bash
kubectl apply -f k8s-health-checker/deploy/autoscaling/hpa-gratitudeapp.yaml
kubectl get hpa -n default
kubectl describe hpa -n default
```

Wait for `TARGETS` to show a numeric value such as `10%/50%`. If it remains
`<unknown>`, verify Metrics Server, CPU requests, and HPA events before testing
load.

### Step 3: Roll out the Sprint 4 health-checker code

Build and push the current health-checker code to ECR:

```bash
sed -i 's/\r$//' k8s-health-checker/scripts/00-build-and-push-healthchecker.sh
bash ./k8s-health-checker/scripts/00-build-and-push-healthchecker.sh
```

Confirm the printed ECR URI matches `image:` in
`k8s-health-checker/deploy/healthchecker/deployment.yaml`, and that its
`imagePullPolicy` is `Always`. Apply the manifest and restart so EKS fetches the
new `latest` image:

```bash
kubectl apply -f k8s-health-checker/deploy/healthchecker/deployment.yaml
kubectl rollout restart deployment/health-checker-deployment -n default
kubectl rollout status deployment/health-checker-deployment -n default --timeout=180s
kubectl get pods -n default -l component=health-checker
```

If the image build is already current, this step can be omitted.

## 4. Verify resource balancing

Start a health-checker port-forward in one WSL terminal and keep it open:

```bash
kubectl port-forward -n default svc/health-checker-cluster-ip-service 8000:8000
```

From a second WSL terminal:

```bash
curl -s http://localhost:8000/api/node-balancing | python3 -m json.tool
curl -s http://localhost:8000/metrics \
  | grep -E 'healthchecker_node_pod_count|healthchecker_node_cpu_capacity_cores|healthchecker_cluster_balance_ratio'
```

The report should list the EKS nodes, readiness, allocatable CPU/memory,
per-node pod counts, and a balance ratio. The ratio is a pod-count balance
indicator, not a guarantee of equal CPU or memory utilization. With only one
node, the implementation reports a ratio of `1.0`.

## 5. Test HPA scale-out and scale-in

Run this only when a brief increase in request traffic is acceptable. Open a
second terminal to observe HPAs:

```bash
kubectl get hpa -n default -w
```

In another terminal, apply the project load generator:

```bash
kubectl apply -f k8s-health-checker/deploy/autoscaling/load-generator.yaml
kubectl rollout status deployment/load-generator -n default --timeout=120s
```

Observe replicas and CPU targets:

```bash
kubectl get hpa -n default
kubectl get deployments api-gateway-deployment client-deployment server-deployment -n default
kubectl get pods -n default
kubectl top pods -n default
```

Scaling is metric- and timing-dependent; it may take a few minutes, and the
load generator may not exceed CPU targets on every cluster. Do not assume it
will reach the configured maximum replica counts.

**Stop the load immediately after observing the response:**

```bash
kubectl delete -f k8s-health-checker/deploy/autoscaling/load-generator.yaml --ignore-not-found
```

Wait for HPA scale-in (the manifest has a 60-second stabilization window):

```bash
kubectl get hpa -n default -w
```

Keep the HPAs in place after the test; they should settle at their configured
minimum replica count. Do not manually scale an HPA-managed Deployment while
the HPA remains active, since the HPA will reconcile replica counts.

## 6. Optional: configure Cluster Autoscaler for EKS

Cluster Autoscaler is **separate from HPA**: HPA adjusts pod replicas;
Cluster Autoscaler adjusts the EC2 Auto Scaling Group when pods cannot be
scheduled or nodes are sufficiently underutilized.

The checked-in `cluster-autoscaler.yaml` is **not ready to apply as-is**:

- The IRSA role annotation is only a commented placeholder.
- The EKS node-group Auto Scaling Group must have the exact discovery tags.
- The checked-in image is `v1.30.0`; Cluster Autoscaler should use a release
  compatible with the Kubernetes minor version of this EKS cluster.
- AWS IAM permissions and the EKS OIDC provider/role trust must be configured.

Do not apply this manifest until all prerequisites below are complete.

1. Check the cluster version and IAM OIDC provider:

   ```bash
   aws eks describe-cluster --name gratitude-health-cluster --region us-east-1 \
     --query 'cluster.version' --output text
   eksctl utils describe-stacks --cluster gratitude-health-cluster --region us-east-1
   ```

   The cluster config enables OIDC, but verify the provider exists and is
   associated with this EKS cluster.

2. Find the managed node group's Auto Scaling Group name:

   ```bash
   aws eks describe-nodegroup \
     --cluster-name gratitude-health-cluster \
     --nodegroup-name default-ng \
     --region us-east-1 \
     --query 'nodegroup.resources.autoScalingGroups[].name' \
     --output text
   ```

3. Confirm that ASG has discovery tags with these exact key/value pairs:

   ```text
   k8s.io/cluster-autoscaler/enabled = true
   k8s.io/cluster-autoscaler/gratitude-health-cluster = owned
   ```

   Add missing tags to the correct ASG using AWS Console or AWS CLI, and verify
   them before continuing. Restrict the Cluster Autoscaler IAM policy's
   mutating actions to this node group's ASG where possible.

4. Create a dedicated IAM role trusted only by the
   `system:serviceaccount:kube-system:cluster-autoscaler` service account.
   Attach a least-privilege autoscaling policy following AWS's current EKS
   Cluster Autoscaler guidance. Do not use `AdministratorAccess`.

5. Create a local copy of
   `k8s-health-checker/deploy/autoscaling/cluster-autoscaler.yaml` and edit the
   copy with the role ARN and a Cluster Autoscaler image compatible with the
   EKS Kubernetes minor version. Review the auto-discovery cluster name and
   flags. Keep account-specific IAM ARNs out of the tracked project file:

   ```bash
   cp k8s-health-checker/deploy/autoscaling/cluster-autoscaler.yaml /tmp/cluster-autoscaler-eks.yaml
   ```

   Edit `/tmp/cluster-autoscaler-eks.yaml` only after IAM, ASG tags, and image
   compatibility are confirmed.

6. Validate the edited manifest and only then apply it:

   ```bash
   kubectl apply --dry-run=server -f /tmp/cluster-autoscaler-eks.yaml
   kubectl apply -f /tmp/cluster-autoscaler-eks.yaml
   kubectl rollout status deployment/cluster-autoscaler -n kube-system --timeout=180s
   kubectl logs -n kube-system deployment/cluster-autoscaler --tail=100
   ```

   After confirming the deployment is healthy, remove the local copy:

   ```bash
   rm -f /tmp/cluster-autoscaler-eks.yaml
   ```

If IAM, tags, or version compatibility are not verified, skip Cluster
Autoscaler. HPA and the balance endpoint can be used without it.

## 7. Troubleshooting and cleanup

### HPA shows `<unknown>` or does not scale

```bash
kubectl top nodes
kubectl top pods -n default
kubectl describe hpa -n default
kubectl get events -n default --sort-by=.lastTimestamp
```

Verify Metrics Server, target Deployment CPU requests, and that the workload
actually receives CPU load.

### Pods remain Pending after HPA scale-out

```bash
kubectl get pods -n default
kubectl describe pod -n default <PENDING_POD_NAME>
kubectl get nodes
```

Without a correctly configured Cluster Autoscaler, extra replicas may remain
Pending when the current EC2 nodes lack capacity. Do not assume HPA creates
nodes.

### Remove test traffic

Always delete the load generator:

```bash
kubectl delete deployment load-generator -n default --ignore-not-found
kubectl get pods -n default -l app=load-generator
```

### Roll back a workload manifest if needed

If a rollout introduces problems, inspect its rollout history and revert only
the affected Deployment:

```bash
kubectl rollout history deployment/client-deployment -n default
kubectl rollout undo deployment/client-deployment -n default
```

## 8. Checklist

- [ ] AWS identity and EKS context are correct; nodes are Ready.
- [ ] `kubectl top` reports node and pod metrics.
- [ ] HPA target workloads have CPU requests and are Ready.
- [ ] All three HPA resources show numeric CPU targets.
- [ ] Health-checker `/api/node-balancing` and balance metrics respond.
- [ ] Load generator was deleted after testing and replicas stabilized.
- [ ] Cluster Autoscaler was skipped or fully configured with matching tags,
      IAM, and a compatible version before deployment.
