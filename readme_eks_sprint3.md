# Sprint 3 — Self-Healing and Chaos Testing on Amazon EKS

This guide rolls out the Sprint 3 health-checker to the existing GratitudeApp
EKS cluster, verifies self-healing and its audit endpoints, and describes an
optional AWS Fault Injection Service (FIS) exercise. It uses Amazon ECR and
does not use Minikube.

> **AWS costs and operational impact:** EKS, EC2 nodes, EBS, NAT gateways,
> ECR storage, and AWS FIS experiments can incur charges. Self-healing deletes
> unhealthy pods and lets their controllers recreate them; this can interrupt
> service availability. Run chaos tests only on a cluster and workload where
> a temporary disruption is acceptable. Clean up test resources afterward.

## Contents

1. [Prerequisites](#1-prerequisites)
2. [Sprint 3 behavior](#2-sprint-3-behavior)
3. [Step-by-step EKS deployment](#3-step-by-step-eks-deployment)
4. [Test crash-loop recovery safely](#4-test-crash-loop-recovery-safely)
5. [Optional: AWS FIS CPU experiment](#5-optional-aws-fis-cpu-experiment)
6. [Troubleshooting](#6-troubleshooting)
7. [Sprint 3 checklist](#7-sprint-3-checklist)

## 1. Prerequisites

Run commands from **Ubuntu/WSL** in the repository root. Sprint 1 and Sprint 2
should already be deployed, including the GratitudeApp, monitoring stack, and
health-checker. Required tools in WSL:

- AWS CLI configured for the account containing the EKS cluster and ECR
- `kubectl`, Docker, and `curl`
- Helm 3.x if you need to install or upgrade the Sprint 2 monitoring stack
- AWS FIS permissions only if you choose the optional FIS experiment

Verify the tools and AWS identity:

```bash
aws --version
kubectl version --client
docker version
aws sts get-caller-identity
```

Use the step-by-step process in [Section 3](#3-step-by-step-eks-deployment).

## 2. Sprint 3 behavior

The existing health-checker source adds:

- Periodic self-healing scans (every 15 seconds) when
  `ENABLE_SELF_HEALING=true`.
- Deletion of unhealthy pods owned by a Deployment/ReplicaSet, allowing the
  owning controller to recreate them. Conditions include `CrashLoopBackOff`,
  selected container errors, repeated OOM/error terminations, and a Running
  pod that is unready with at least five restarts.
- Cleanup of pods whose actual Kubernetes status is `Evicted`.
- A 45-second per-workload cooldown for the normal unhealthy-pod recovery path.
- `GET /api/healing-log`, `POST /api/heal`, and the
  `healthchecker_healing_actions_total` Prometheus counter.

The audit log and counter are in-memory. They are reset when the health-checker
process restarts; they are not a durable incident history. The Evicted-pod
cleanup path is not restricted to Deployment-owned pods.

Relevant implementation files:

- `k8s-health-checker/healthchecker-app/healer.py`
- `k8s-health-checker/healthchecker-app/monitor.py`
- `k8s-health-checker/healthchecker-app/main.py`
- `k8s-health-checker/deploy/healthchecker/rbac.yaml`
- `k8s-health-checker/deploy/healthchecker/deployment.yaml`

The Deployment manifest enables self-healing. Keep the health-checker
port-forward bound to localhost; do not expose its healing endpoint publicly.

## 3. Step-by-step EKS deployment

These steps update only the health-checker to Sprint 3. They do not upgrade
GratitudeApp's microservices or reinstall the Sprint 2 monitoring stack.
Run commands in Ubuntu/WSL, from the repository root:

```bash
cd /mnt/c/Users/CBhalla/Desktop/herovired/capstone_eks/Capstone_Project_HeroVired
```

### Step 1: Verify AWS identity and cluster access

From PowerShell, open WSL with `wsl` if needed. Check the active AWS identity,
configure the WSL kubeconfig, and verify the context and nodes:

```bash
aws sts get-caller-identity
aws eks update-kubeconfig --region us-east-1 --name gratitude-health-cluster
kubectl config current-context
kubectl get nodes
```

Stop if the AWS account is unexpected, the context is not the EKS cluster, or
any node is not `Ready`.

### Step 2: Check the Sprint 1/2 baseline

```bash
kubectl get pods -n default
kubectl get pods -n monitoring
```

Resolve existing unhealthy application or monitoring pods before deployment.
This ensures the health-checker rollout starts from a known-good state.

### Step 3: Build and push the Sprint 3 image

The Python files are packaged into a container image; they are not applied
directly with `kubectl`. Build the current source and push it to ECR:

```bash
bash ./k8s-health-checker/scripts/00-build-and-push-healthchecker.sh
```

The script pushes the image tagged `latest` to `us-east-1`. Docker must work
inside WSL, and the AWS identity needs ECR push permissions. Confirm the image
exists:

```bash
aws ecr describe-images \
  --repository-name gratitude-health-checker \
  --region us-east-1 \
  --query 'imageDetails[].imageTags[]'
```

### Step 4: Verify the EKS Deployment manifest

Before applying it, inspect
`k8s-health-checker/deploy/healthchecker/deployment.yaml`. Confirm:

- `image:` matches the ECR URI printed by the build script and account.
- `imagePullPolicy: Always` is set, so EKS pulls the pushed `latest` image.
- `ENABLE_SELF_HEALING` is `"true"`.

The EKS manifest must not use `imagePullPolicy: Never`; that policy prevents
the node from pulling the image from ECR. Ensure the EKS worker-node role can
pull from this ECR repository.

### Step 5: Apply RBAC and roll out the health-checker

Apply the health-checker permissions and Deployment:

```bash
kubectl apply -f k8s-health-checker/deploy/healthchecker/rbac.yaml
kubectl apply -f k8s-health-checker/deploy/healthchecker/deployment.yaml
```

Restart the Deployment to force a fresh pull of the just-pushed `latest` image,
then wait for the new pod to become Ready:

```bash
kubectl rollout restart deployment/health-checker-deployment -n default
kubectl rollout status deployment/health-checker-deployment -n default --timeout=180s
kubectl get pods -n default -l component=health-checker
kubectl logs -n default deployment/health-checker-deployment --tail=50
```

Do not rerun `03-deploy-monitoring.sh` for this image-only update if Sprint 2's
monitoring stack is already installed; that script also runs Helm to upgrade or
install Prometheus/Grafana. If monitoring is not installed, first follow the
Sprint 2 EKS guide.

### Step 6: Verify the health-checker API and metric endpoint

In one WSL terminal, start the port-forward and leave it running:

```bash
kubectl port-forward -n default svc/health-checker-cluster-ip-service 8000:8000
```

In a second WSL terminal:

```bash
curl http://localhost:8000/healthz
curl -s http://localhost:8000/api/healing-log
curl -s http://localhost:8000/metrics | grep healthchecker_healing_actions_total
```

The health endpoint should return `{"status":"ok"}`. The healing log can
initially be empty, and the counter may have no sample until an action occurs.
Keep this port-forward open for the test in Step 7.

### Step 7: Optionally configure FIS namespace permissions

Skip this if you are not using AWS FIS. Apply only when an FIS experiment has
been approved and the required AWS-side configuration is prepared:

```bash
kubectl apply -f k8s-health-checker/chaos/rbac.yml
kubectl get serviceaccount fis-sa -n default
kubectl get role,rolebinding -n default
```

The namespace Role permits powerful operations inside `default`. Do not apply
the repository's `fis-sa-cluster-admin.yml` or
`fis-experiement-cluster-admin.yml`; they grant cluster-admin. See
[Section 5](#5-optional-aws-fis-cpu-experiment) for FIS setup notes.

### Step 8: Test self-healing and clean up

When ready, run the isolated CrashLoop test in
[Section 4](#4-test-crash-loop-recovery-safely). The test runs in `default`,
may briefly generate restarts, and must be deleted after verification. Do not
run it on a production or shared cluster.

## 4. Test crash-loop recovery safely

This test creates a single failing pod managed by a disposable Deployment in
the `default` namespace. The health-checker may delete/recreate its pod as it
crash-loops. It does not target GratitudeApp deployments.

Apply the test Deployment:

```bash
cat <<'EOF' | kubectl apply -f -
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
          command: ["/bin/sh", "-c", "echo 'Test failure'; exit 1"]
EOF
```

Watch the test pod and inspect health-checker logs:

```bash
kubectl get pods -n default -l app=chaos-crashloop-test -w
```

In another terminal:

```bash
kubectl logs -n default deployment/health-checker-deployment --since=5m
curl -s http://localhost:8000/api/healing-log
curl -s http://localhost:8000/metrics | grep healthchecker_healing_actions_total
```

Allow time for the container to enter a detected failing state and for the
poller/cooldown to act. Then remove the test Deployment:

```bash
kubectl delete deployment chaos-crashloop-test -n default
```

### Evicted-pod behavior

Kubernetes ignores user-supplied pod `status` during normal pod creation, so
applying a manifest that claims a pod is already `Evicted` is not a reliable
test. Do not deliberately create node memory or disk pressure to force eviction
on this shared EKS cluster. If an eviction happens naturally, inspect the
health-checker's audit log and cluster events after it cleans up the terminated
pod.

## 5. Optional: AWS FIS CPU experiment

The repository's `k8s-health-checker/chaos/fis-template.json` is an example,
not a ready-to-run EKS template. It contains an old cluster identifier and an
example IAM role ARN. Do not submit it unchanged.

This optional exercise uses AWS Fault Injection Service (FIS) against the EKS
cluster. It does not use Minikube.

Before creating an experiment:

1. Confirm you have approval to inject CPU load into the selected EKS workload.
   Do not run an experiment on a production/shared cluster without explicit
   authorization and a recovery plan.
2. Follow current AWS documentation to configure the EKS FIS integration and
   a dedicated IAM experiment role. Set the template's `roleArn` to that role's
   ARN, not an IAM user ARN or the EKS node role.
3. Edit `k8s-health-checker/chaos/fis-template.json`: change
   `clusterIdentifier` from `mck-demo` to `gratitude-health-cluster`, set the
   correct IAM role ARN, and review the target selector and action parameters.
4. The example uses `stopConditions: [{"source":"none"}]`, which has no
   CloudWatch alarm stop condition. Configure a meaningful CloudWatch alarm
   stop condition before submitting, and verify it is active and wired to the
   experiment.
5. Confirm `fis-sa` and the least-privilege permissions required for the
   selected FIS action. The repository's namespace Role is broad within
   `default`; do not apply its cluster-admin binding manifests.
6. Keep the experiment limited to one intended `server-deployment` pod and
   the minimum duration needed. Confirm the application can tolerate it,
   identify an operator to monitor it, and know how to stop the experiment.

Validate the edited JSON syntax and inspect the full template before submitting:

```bash
python3 -m json.tool k8s-health-checker/chaos/fis-template.json
```

After the FIS role, EKS integration, target, permissions, and stop condition
have been independently verified, create the template:

```bash
aws fis create-experiment-template \
  --cli-input-json file://k8s-health-checker/chaos/fis-template.json \
  --region us-east-1
```

Review the returned template ID and configuration. Do not start until the
experiment has been approved and the target and stop condition have been
verified. When ready:

```bash
aws fis start-experiment \
  --experiment-template-id <EXPERIMENT_TEMPLATE_ID> \
  --region us-east-1
```

Monitor the experiment in the AWS FIS console or with
`aws fis get-experiment --id EXPCC4d1Y8aiG8hB4W --region us-east-1`. The ID
above is the experiment ID returned by `start-experiment`. To stop the running
experiment from WSL, run:

```bash
aws fis stop-experiment --id EXPCC4d1Y8aiG8hB4W --region us-east-1
```

You can also stop it in the AWS Console: open **AWS Fault Injection Service
(FIS) → Experiments**, select the running experiment, and choose **Stop**.
Confirm its state with `get-experiment`; AWS FIS experiments may incur charges.

## 6. Troubleshooting

### Health-checker cannot pull its ECR image

```bash
kubectl describe pod -n default -l component=health-checker
kubectl get events -n default --sort-by=.lastTimestamp
```

Check that the image URI and region are correct, the image exists in ECR, and
the EKS node role can pull it. After pushing a new image with the same tag,
restart the Deployment to force a pull.

### Healing endpoint or metrics are unavailable

```bash
kubectl get pods -n default -l component=health-checker
kubectl logs -n default deployment/health-checker-deployment --tail=100
kubectl get endpoints -n default health-checker-cluster-ip-service
```

Confirm the health-checker pod is Ready and the port-forward is still running.

### Health-checker cannot delete a failing pod

```bash
kubectl auth can-i delete pods \
  --as=system:serviceaccount:default:health-checker -n default
kubectl get clusterrolebinding health-checker-binding
```

The authorization check should return `yes`. Do not solve permission errors by
granting `cluster-admin`; review and correct the health-checker RBAC instead.

### No healing action is recorded

Check that `ENABLE_SELF_HEALING` is `true`, the health-checker has permission to
list/delete pods, and the test pod is Deployment/ReplicaSet-owned and in a
condition handled by `healer.py`. Unmanaged crash-loop pods are intentionally
not deleted by the normal recovery path.

## 7. Sprint 3 checklist

- [ ] EKS context points to `gratitude-health-cluster`; nodes are Ready.
- [ ] Updated health-checker image was built and pushed to ECR.
- [ ] Deployment uses the ECR image with `imagePullPolicy: Always`.
- [ ] Health-checker Deployment is Ready with Sprint 3 code.
- [ ] `GET /api/healing-log` and `/metrics` are reachable using a local
      port-forward.
- [ ] The disposable CrashLoopBackOff test records a healing action.
- [ ] The test Deployment was deleted after verification.
- [ ] No cluster-admin FIS bindings were added as a shortcut.
- [ ] If AWS FIS was used, the experiment configuration was reviewed,
      bounded, monitored, and stopped/finished safely.
