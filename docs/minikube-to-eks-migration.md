# Migrating from Local Minikube to Amazon EKS

This guide walks through transferring the GratitudeApp + Health-Checker deployment
from a local minikube cluster to the production EKS cluster (`gratitude-health-cluster`).

---

## Overview

| Aspect | Minikube | Amazon EKS |
|---|---|---|
| Control plane | Local VM | AWS-managed |
| Storage | `hostPath` / `standard` StorageClass | EBS gp3 via `aws-ebs-csi-driver` |
| Ingress | `minikube tunnel` + nginx addon | ingress-nginx via AWS Network Load Balancer |
| Image registry | Local Docker daemon / DockerHub | Amazon ECR (health-checker only) |
| Secrets | Plain YAML applied locally | Same YAML — never commit real values |
| Networking | `NodePort` / port-forward | ClusterIP + Ingress (NLB external IP) |

The GratitudeApp microservices use **existing Docker Hub images** (`prashantdey/merndemoapp:*`)
and require no rebuilding. Only the health-checker image needs to be pushed to ECR.

---

## Prerequisites

Install and configure the following tools before you begin:

```bash
# Verify each tool is available
aws --version          # AWS CLI 2.x, configured with valid credentials
eksctl version         # 0.170+
kubectl version        # 1.28+
helm version           # 3.x
docker --version       # for building the health-checker image
```

Configure AWS credentials with permissions to create EKS, VPC, EC2, IAM, and ECR resources:

```bash
aws configure
# AWS Access Key ID:     <your key>
# AWS Secret Access Key: <your secret>
# Default region:        us-east-1
# Default output format: json

# Verify identity
aws sts get-caller-identity
```

---

## Step 1 — Update Secrets for Production

The manifest files in `gratitude-k8s/` contain placeholder secrets. Update them
**before** applying to EKS. See [docs/SECRETS.md](SECRETS.md) for the full list.

### database-secret.yml

```yaml
# gratitude-k8s/database-secret.yml
# Values must be base64-encoded: echo -n 'mypassword' | base64
apiVersion: v1
kind: Secret
metadata:
  name: pgpassword
type: Opaque
data:
  PGPASSWORD: <base64-encoded-password>
```

### openai-api-secret.yml

```yaml
# gratitude-k8s/openai-api-secret.yml
apiVersion: v1
kind: Secret
metadata:
  name: openai-api-secret
type: Opaque
data:
  OPENAI_API_KEY: <base64-encoded-key>
```

> **Never commit real secret values.** The `.gitignore` in this repo excludes files
> matching `*secret*.yml` that contain real keys. Use `openai-api-secret.example.yml`
> as a reference template.

---

## Step 2 — EKS-Specific Manifest Differences

Minikube and EKS require a few manifest-level changes. The `gratitude-k8s/` and
`k8s-health-checker/` directories already contain EKS-ready versions of all files.
The table below explains what differs from a vanilla minikube setup.

### StorageClass

Minikube uses the `standard` (hostPath) default StorageClass. EKS requires the
`gp3` StorageClass backed by the EBS CSI driver:

```yaml
# gratitude-k8s/storageclass-gp3-default.yml  (already EKS-ready)
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: gp3
  annotations:
    storageclass.kubernetes.io/is-default-class: "true"
provisioner: ebs.csi.aws.com
volumeBindingMode: WaitForFirstConsumer
allowVolumeExpansion: true
parameters:
  type: gp3
```

Apply this **before** the Postgres PVC or it will bind to the wrong provisioner.

### Ingress

On minikube you would run `minikube addons enable ingress` and `minikube tunnel`.
On EKS, ingress-nginx is installed via Helm and exposed through an AWS NLB:

```bash
helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx --create-namespace \
  --set controller.service.type=LoadBalancer \
  --set controller.service.annotations."service\.beta\.kubernetes\.io/aws-load-balancer-type"=nlb
```

The `ingress-service.yml` already uses `ingressClassName: nginx` and works with
both environments without modification.

### PersistentVolumeClaim

Minikube PVCs bind immediately; EKS with `volumeBindingMode: WaitForFirstConsumer`
delays binding until a pod is scheduled. No manifest change is needed — just be
aware that `kubectl get pvc` will show `Pending` until Postgres starts.

---

## Step 3 — Build and Push the Health-Checker Image to ECR

The GratitudeApp services use pre-built Docker Hub images and need no change.
The health-checker image must be built locally and pushed to Amazon ECR.

```bash
# From the repo root
cd k8s-health-checker
./scripts/00-build-and-push-healthchecker.sh
```

The script:
1. Creates an ECR repository named `gratitude-health-checker` (if it doesn't exist).
2. Authenticates Docker to your ECR registry.
3. Builds the image from `healthchecker-app/Dockerfile`.
4. Tags and pushes `<account>.dkr.ecr.us-east-1.amazonaws.com/gratitude-health-checker:latest`.
5. Prints the full image URI.

After the push completes, update the image field in the deployment manifest:

```yaml
# deploy/healthchecker/deployment.yaml — update this line:
image: <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/gratitude-health-checker:latest
```

---

## Step 4 — Provision the EKS Cluster

```bash
cd k8s-health-checker
./scripts/01-provision-eks.sh
```

This runs `eksctl create cluster -f eksctl/cluster.yaml` which provisions:

| Resource | Value |
|---|---|
| Cluster name | `gratitude-health-cluster` |
| Region | `us-east-1` |
| Kubernetes version | 1.30 |
| Node group | 2x `t3.medium` (min 1, max 3) |
| OIDC provider | Enabled (required for IRSA) |
| NAT gateway | Single (cost optimization) |
| EBS CSI driver | Installed as an EKS addon with IAM role |

Cluster creation takes **15–20 minutes**. eksctl automatically updates your
`~/.kube/config` so `kubectl` is ready immediately after.

Verify cluster access:

```bash
kubectl get nodes
# NAME                          STATUS   ROLES    AGE   VERSION
# ip-192-168-xx-xx.ec2.internal Ready    <none>   2m    v1.30.x
# ip-192-168-xx-xx.ec2.internal Ready    <none>   2m    v1.30.x
```

---

## Step 5 — Deploy GratitudeApp

```bash
./scripts/02-deploy-gratitudeapp.sh
```

This applies manifests in dependency order:

```
StorageClass (gp3)
  └─> Secrets + ConfigMaps (database-secret, openai-api-secret, postgres-init-config)
        └─> Postgres (PVC → Deployment → Service)
              └─> Backend microservices (api-gateway, entries, moods-api/service,
                                          stats-api/service, files-service, server)
                    └─> Frontend client
                          └─> Ingress
                                └─> DB migration job (one-time)
```

Wait for pods to become Ready:

```bash
kubectl get pods -w
# All pods should reach Running/Completed within 3-5 minutes
```

Get the external NLB hostname (may take 2–3 minutes to provision):

```bash
kubectl get svc -n ingress-nginx ingress-nginx-controller
# EXTERNAL-IP will show something like:
# a1b2c3d4e5f6.elb.us-east-1.amazonaws.com
```

Open `http://<EXTERNAL-IP>` in a browser to verify GratitudeApp is live.

---

## Step 6 — Deploy the Health-Checker and Monitoring Stack

```bash
./scripts/03-deploy-monitoring.sh
```

This applies:
- `deploy/healthchecker/rbac.yaml` — ServiceAccount, ClusterRole, ClusterRoleBinding
- `deploy/healthchecker/deployment.yaml` — Health-checker Deployment + ClusterIP Service
- `kube-prometheus-stack` via Helm (Prometheus, Grafana, Alertmanager)

Access services locally via port-forward (the health-checker and Grafana are internal):

```bash
# Health-checker API
kubectl port-forward -n default svc/health-checker-cluster-ip-service 8000:8000 &
curl http://localhost:8000/api/summary

# Grafana dashboard
kubectl port-forward -n monitoring svc/monitoring-grafana 3001:80 &
# Open http://localhost:3001 — credentials: admin / changeme
```

---

## Step 7 — Verify the Full Stack

Run the following checks to confirm everything is healthy:

```bash
# All pods in default namespace should be Running
kubectl get pods -n default

# All monitoring pods should be Running
kubectl get pods -n monitoring

# Ingress should show the NLB address
kubectl get ingress

# Health-checker summary (requires port-forward from Step 6)
curl http://localhost:8000/api/summary

# Check Prometheus targets are scraped
curl http://localhost:8000/metrics | grep healthchecker_
```

Expected pod states:

| Pod | Expected Status |
|---|---|
| `postgres-*` | Running |
| `api-gateway-*` | Running |
| `server-deployment-*` | Running |
| `client-*` | Running |
| `entries-deployment-*` | Running |
| `moods-api-*`, `moods-service-*` | Running |
| `stats-api-*`, `stats-service-*` | Running |
| `files-service-*` | Running (S3 calls fail until IRSA is configured — see Known Limitations) |
| `health-checker-deployment-*` | Running |
| `monitoring-grafana-*` | Running |
| `monitoring-prometheus-*` | Running |

---

## Key Differences vs. Minikube — Quick Reference

| Topic | Minikube command | EKS equivalent |
|---|---|---|
| Start cluster | `minikube start` | `eksctl create cluster -f eksctl/cluster.yaml` |
| Enable ingress | `minikube addons enable ingress` | `helm install ingress-nginx ...` |
| Access app | `minikube tunnel` | NLB external hostname (auto-provisioned) |
| Access internal service | `minikube service <svc>` | `kubectl port-forward svc/<svc> <port>:<port>` |
| Persistent storage | `standard` (hostPath) | `gp3` (EBS via CSI driver) |
| Image registry | Local daemon or DockerHub | Amazon ECR (health-checker) / DockerHub (GratitudeApp) |
| Stop cluster | `minikube stop` | `eksctl delete cluster -f eksctl/cluster.yaml` |
| Delete cluster | `minikube delete` | `./scripts/99-teardown.sh` |

---

## Teardown

Run teardown immediately after demos or screenshots to avoid ongoing AWS charges.

```bash
./scripts/99-teardown.sh
```

This removes (in order):
1. Helm releases: `monitoring`, `ingress-nginx`
2. All GratitudeApp Kubernetes resources
3. Health-checker Deployment and RBAC
4. The EKS cluster, VPC, NAT gateway, and NLB via `eksctl delete cluster`

**Estimated cost for a full run (provision → deploy → demo → teardown): $5–15**
based on how long the cluster remains live.

After teardown, verify in the AWS Console that no stray resources remain:
- EKS clusters
- EC2 instances
- VPC / NAT Gateways
- Elastic Load Balancers (NLB)
- EBS volumes
- ECR repositories (if no longer needed)

---

## Known Limitations

- **files-service S3/IRSA**: S3 upload/download calls fail until an IAM role with S3
  permissions is created and bound to `files-service-sa` via IRSA. See the GratitudeApp
  source README for the IRSA setup steps.
- **OpenAI key**: AI-assisted journal features require a real OpenAI API key in
  `gratitude-k8s/openai-api-secret.yml`. See [docs/SECRETS.md](SECRETS.md).
- **Grafana default password**: Change the Grafana `admin` password from `changeme`
  before exposing Grafana externally.
- **Single NAT gateway**: The cluster uses one NAT gateway across AZs for cost savings.
  In production, use one per AZ for high availability.
