# Sprint 1 — Step-by-Step Execution Guide

**Goal:** Provision a production-like EKS cluster on AWS, deploy all 9 GratitudeApp
microservices, build and deploy the health-checker service, and stand up the
Prometheus / Grafana / Alertmanager monitoring stack — end to end, from zero.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Repository Setup](#2-repository-setup)
3. [Provision the EKS Cluster](#3-provision-the-eks-cluster)
4. [Configure Secrets](#4-configure-secrets)
5. [Deploy GratitudeApp](#5-deploy-gratitudeapp)
6. [Build and Push the Health-Checker Image](#6-build-and-push-the-health-checker-image)
7. [Update the Deployment Manifest](#7-update-the-deployment-manifest)
8. [Deploy the Health-Checker and Monitoring Stack](#8-deploy-the-health-checker-and-monitoring-stack)
9. [Verify Everything](#9-verify-everything)
10. [Teardown](#10-teardown)

---

## 1. Prerequisites

Install and verify each tool before running any scripts.

### 1.1 AWS CLI v2

```bash
# macOS
brew install awscli

# Linux
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip
unzip awscliv2.zip && sudo ./aws/install

# Verify
aws --version
# Expected: aws-cli/2.x.x ...
```

Configure with your IAM credentials (needs permissions for EKS, EC2, VPC, IAM, ECR):

```bash
aws configure
# AWS Access Key ID     [None]: <your-access-key-id>
# AWS Secret Access Key [None]: <your-secret-access-key>
# Default region name   [None]: us-east-1
# Default output format [None]: json

# Verify identity
aws sts get-caller-identity
```

Expected output:
```json
{
    "UserId": "AIDAXXXXXXXXXXXXXXXXX",
    "Account": "123456789012",
    "Arn": "arn:aws:iam::123456789012:user/your-user"
}
```

### 1.2 eksctl

```bash
# macOS
brew tap weaveworks/tap
brew install weaveworks/tap/eksctl

# Linux
curl --silent --location "https://github.com/weaveworks/eksctl/releases/latest/download/eksctl_$(uname -s)_amd64.tar.gz" | tar xz -C /tmp
sudo mv /tmp/eksctl /usr/local/bin

# Verify
eksctl version
# Expected: 0.x.x
```

### 1.3 kubectl

```bash
# macOS
brew install kubectl

# Linux
curl -LO "https://dl.k8s.io/release/$(curl -sL https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl && sudo mv kubectl /usr/local/bin/

# Verify
kubectl version --client
```

### 1.4 Helm 3

```bash
# macOS
brew install helm

# Linux
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# Verify
helm version
# Expected: version.BuildInfo{Version:"v3.x.x" ...}
```

### 1.5 Docker

```bash
# macOS — install Docker Desktop from https://www.docker.com/products/docker-desktop/

# Linux (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install -y docker.io
sudo usermod -aG docker $USER
newgrp docker

# Verify
docker --version
docker info | grep "Server Version"
```

### 1.6 Python 3.12 (for local health-checker development only)

```bash
# macOS
brew install python@3.12

# Linux
sudo apt-get install -y python3.12 python3.12-venv python3-pip

# Verify
python3 --version
```

---

## 2. Repository Setup

```bash
# Clone the repository
git clone <your-repo-url>
cd Capstone_Project_HeroVired

# Switch to the sprint1 branch
git checkout sprint1

# Confirm the project structure is intact
ls k8s-health-checker/
# Expected output:
# healthchecker-app/  gratitude-k8s/  chaos/  eksctl/
# deploy/  scripts/  docs/  README.md
```

Make all scripts executable:

```bash
chmod +x k8s-health-checker/scripts/*.sh
```

---

## 3. Provision the EKS Cluster

This step creates the full AWS infrastructure: VPC, subnets, NAT gateway, EKS
control plane, a managed node group (2× t3.medium), OIDC provider, EBS CSI
driver addon, and installs ingress-nginx via Helm.

**Expected time: 15–20 minutes.**

```bash
./k8s-health-checker/scripts/01-provision-eks.sh
```

What the script does internally:

```bash
# 1. Create the cluster from the eksctl config
eksctl create cluster -f k8s-health-checker/eksctl/cluster.yaml
# Config: us-east-1, 2x t3.medium, single NAT gateway, OIDC, EBS CSI addon

# 2. eksctl automatically updates ~/.kube/config — verify access
kubectl get nodes
# Expected: 2 nodes in Ready state

# 3. Check EBS CSI driver is running
kubectl get pods -n kube-system | grep ebs-csi

# 4. Add and install ingress-nginx (exposed as AWS NLB)
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update
helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx --create-namespace \
  --set controller.service.type=LoadBalancer \
  --set controller.service.annotations."service\.beta\.kubernetes\.io/aws-load-balancer-type"=nlb \
  --set controller.resources.requests.cpu=100m \
  --set controller.resources.requests.memory=128Mi

# 5. Wait for the controller pod to be ready
kubectl wait --for=condition=Ready pods --all -n ingress-nginx --timeout=180s
```

### Verify cluster health

```bash
# All nodes should be Ready
kubectl get nodes -o wide

# EBS CSI pods should be Running
kubectl get pods -n kube-system -l app.kubernetes.io/name=aws-ebs-csi-driver

# ingress-nginx controller should be Running
kubectl get pods -n ingress-nginx

# NLB provisioning (copy the EXTERNAL-IP — needed later to reach GratitudeApp)
kubectl get svc -n ingress-nginx ingress-nginx-controller
```

Expected `kubectl get nodes` output:
```
NAME                          STATUS   ROLES    AGE   VERSION
ip-192-168-x-x.ec2.internal   Ready    <none>   3m    v1.30.x
ip-192-168-x-x.ec2.internal   Ready    <none>   3m    v1.30.x
```

---

## 4. Configure Secrets

Before deploying GratitudeApp, update the two secret files with real values.

### 4.1 Postgres password

The default password is `postgres` (base64: `cG9zdGdyZXM=`).
To use a custom password:

```bash
# Generate a new base64-encoded password
echo -n "your-secure-password" | base64
# e.g. eW91ci1zZWN1cmUtcGFzc3dvcmQ=
```

Open `k8s-health-checker/gratitude-k8s/database-secret.yml` and update the
`PGPASSWORD` field with your output:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: database-secret
type: Opaque
data:
  PGPASSWORD: eW91ci1zZWN1cmUtcGFzc3dvcmQ=   # ← replace this
```

### 4.2 OpenAI API key (optional)

Open `k8s-health-checker/gratitude-k8s/openai-api-secret.yml`:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: openai-api
type: Opaque
stringData:
  OPENAI_API_KEY: "sk-...your-real-key..."    # ← replace this
```

> **Note:** If you skip this, the AI-assisted journal features will return
> errors but the rest of GratitudeApp (entries, moods, stats, health-checker,
> monitoring) will work normally.

---

## 5. Deploy GratitudeApp

This deploys all 9 microservices and PostgreSQL in the correct dependency order.

```bash
./k8s-health-checker/scripts/02-deploy-gratitudeapp.sh
```

What the script does internally (in order):

```bash
K8S_DIR="k8s-health-checker/gratitude-k8s"

# Step 1 — Storage class, secrets, config
kubectl apply -f $K8S_DIR/storageclass-gp3-default.yml
kubectl apply -f $K8S_DIR/database-secret.yml
kubectl apply -f $K8S_DIR/postgres-init-config.yml
kubectl apply -f $K8S_DIR/openai-api-secret.yml

# Step 2 — Postgres (PVC → Deployment → Service)
kubectl apply -f $K8S_DIR/database-persistent-volume-claim.yml
kubectl apply -f $K8S_DIR/postgres-deployment.yml
kubectl apply -f $K8S_DIR/postgres-cluster-ip-service.yml
kubectl wait --for=condition=Ready pods -l component=postgres --timeout=180s

# Step 3 — Backend microservices
kubectl apply -f $K8S_DIR/api-gateway-deployment.yml
kubectl apply -f $K8S_DIR/api-gateway-cluster-ip-service.yml
kubectl apply -f $K8S_DIR/entries-deployment.yml
kubectl apply -f $K8S_DIR/entries-cluster-ip-service.yml
kubectl apply -f $K8S_DIR/moods-api-deployment.yml
kubectl apply -f $K8S_DIR/moods-api-cluster-ip-service.yml
kubectl apply -f $K8S_DIR/moods-service-deployment.yml
kubectl apply -f $K8S_DIR/moods-service-cluster-ip-service.yml
kubectl apply -f $K8S_DIR/stats-api-deployment.yml
kubectl apply -f $K8S_DIR/stats-api-cluster-ip-service.yml
kubectl apply -f $K8S_DIR/stats-service-deployment.yml
kubectl apply -f $K8S_DIR/stats-service-cluster-ip-service.yml
kubectl apply -f $K8S_DIR/files-service-deployment.yml
kubectl apply -f $K8S_DIR/files-service-cluster-ip-service.yml
kubectl apply -f $K8S_DIR/server-deployment.yml
kubectl apply -f $K8S_DIR/server-cluster-ip-service.yml

# Step 4 — Frontend client
kubectl apply -f $K8S_DIR/client-deployment.yml
kubectl apply -f $K8S_DIR/client-cluster-ip-service.yml
kubectl apply -f $K8S_DIR/client-service.yml

# Step 5 — Ingress
kubectl apply -f $K8S_DIR/ingress-service.yml

# Step 6 — One-time DB migration job
kubectl apply -f $K8S_DIR/postgres-migrate-job.yml

# Step 7 — Wait for all pods
kubectl wait --for=condition=Ready pods --all -n default --timeout=300s
```

### Verify GratitudeApp

```bash
# All pods in the default namespace should be Running
kubectl get pods -n default

# Check the ingress rule
kubectl get ingress -n default

# Get the NLB hostname (may take 2-3 minutes to provision)
kubectl get svc -n ingress-nginx ingress-nginx-controller
# Copy the EXTERNAL-IP value — this is your app's public URL

# Test the app is reachable (replace <NLB_HOSTNAME> with the EXTERNAL-IP above)
curl -I http://<NLB_HOSTNAME>
# Expected: HTTP/1.1 200 OK (or a redirect to the React frontend)
```

Expected `kubectl get pods` output (all should be `Running 1/1`):
```
NAME                                    READY   STATUS    RESTARTS   AGE
api-gateway-deployment-xxx              1/1     Running   0          2m
client-deployment-xxx                   1/1     Running   0          2m
entries-deployment-xxx                  1/1     Running   0          2m
files-service-deployment-xxx            1/1     Running   0          2m
moods-api-deployment-xxx                1/1     Running   0          2m
moods-service-deployment-xxx            1/1     Running   0          2m
postgres-deployment-xxx                 1/1     Running   0          4m
server-deployment-xxx                   1/1     Running   0          2m
stats-api-deployment-xxx                1/1     Running   0          2m
stats-service-deployment-xxx            1/1     Running   0          2m
```

---

## 6. Build and Push the Health-Checker Image

The health-checker is a Python/FastAPI application. It must be containerised and
pushed to Amazon ECR so the Kubernetes cluster can pull it.

```bash
./k8s-health-checker/scripts/00-build-and-push-healthchecker.sh
```

What the script does internally:

```bash
REPO_NAME="gratitude-health-checker"
AWS_REGION="us-east-1"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${REPO_NAME}"

# 1. Create ECR repository (if it doesn't exist yet)
aws ecr create-repository \
  --repository-name "$REPO_NAME" \
  --region "$AWS_REGION"

# 2. Authenticate Docker to ECR
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin \
    "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# 3. Build the image from the Dockerfile
docker build -t "${REPO_NAME}:latest" k8s-health-checker/healthchecker-app/

# 4. Tag and push to ECR
docker tag "${REPO_NAME}:latest" "${ECR_URI}:latest"
docker push "${ECR_URI}:latest"
```

The script prints the full image URI at the end:
```
==> Done. Image pushed to:
    123456789012.dkr.ecr.us-east-1.amazonaws.com/gratitude-health-checker:latest
```

**Copy that URI — you need it in the next step.**

### Verify the image is in ECR

```bash
aws ecr list-images \
  --repository-name gratitude-health-checker \
  --region us-east-1
```

Expected output:
```json
{
    "imageIds": [
        { "imageDigest": "sha256:...", "imageTag": "latest" }
    ]
}
```

---

## 7. Update the Deployment Manifest

Open `k8s-health-checker/deploy/healthchecker/deployment.yaml` and replace the
placeholder image with the URI printed by the previous step:

```yaml
containers:
  - name: health-checker
    image: 123456789012.dkr.ecr.us-east-1.amazonaws.com/gratitude-health-checker:latest
    # ↑ replace <YOUR_ECR_OR_DOCKERHUB_IMAGE>:latest with your actual ECR URI
```

Save the file.

---

## 8. Deploy the Health-Checker and Monitoring Stack

```bash
./k8s-health-checker/scripts/03-deploy-monitoring.sh
```

What the script does internally:

```bash
# 1. Apply RBAC — ServiceAccount, ClusterRole, ClusterRoleBinding
kubectl apply -f k8s-health-checker/deploy/healthchecker/rbac.yaml

# 2. Deploy health-checker (Deployment + ClusterIP Service)
kubectl apply -f k8s-health-checker/deploy/healthchecker/deployment.yaml

# 3. Add the prometheus-community Helm repo
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# 4. Install kube-prometheus-stack (Prometheus + Grafana + Alertmanager)
#    with the cost-tuned values (512Mi Prometheus, 256Mi Grafana, gp3 PVC, 3-day retention)
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  -f k8s-health-checker/deploy/prometheus/prometheus-values.yaml

# 5. Wait for readiness
kubectl wait --for=condition=Ready pods -l component=health-checker -n default --timeout=180s
kubectl wait --for=condition=Ready pods --all -n monitoring --timeout=300s
```

---

## 9. Verify Everything

### 9.1 Pod status across all namespaces

```bash
# default namespace — GratitudeApp + health-checker
kubectl get pods -n default

# monitoring namespace — Prometheus, Grafana, Alertmanager
kubectl get pods -n monitoring

# ingress-nginx namespace
kubectl get pods -n ingress-nginx
```

All pods should show `1/1 Running` (or `Completed` for the migration job).

### 9.2 Health-checker API

```bash
# Open a port-forward to the health-checker service
kubectl port-forward -n default svc/health-checker-cluster-ip-service 8000:8000 &

# Liveness probe
curl http://localhost:8000/healthz
# Expected: {"status":"ok"}

# List cluster nodes
curl http://localhost:8000/api/nodes | python3 -m json.tool
# Expected: {"nodes": [{"name": "ip-...", "ready": "True"}, ...]}

# List all pods in the default namespace
curl http://localhost:8000/api/pods | python3 -m json.tool
# Expected: {"pods": [{...}, {...}, ...]}  — all 10 GratitudeApp pods

# List deployments
curl http://localhost:8000/api/deployments | python3 -m json.tool
# Expected: each deployment shows "desired" == "available"

# Full summary (also triggers an immediate Prometheus metrics update)
curl http://localhost:8000/api/summary | python3 -m json.tool

# Raw Prometheus metrics
curl http://localhost:8000/metrics
# Expected: lines like:
# healthchecker_node_ready{node="ip-..."} 1.0
# healthchecker_pod_phase_running{namespace="default",pod="..."} 1.0
# healthchecker_deployment_available_replicas{...} 1.0
```

### 9.3 Grafana dashboard

```bash
# Port-forward Grafana
kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80 &

# Open in browser
open http://localhost:3000
# Username: admin
# Password: changeme  (set in deploy/prometheus/prometheus-values.yaml)
```

Once logged in:
1. Go to **Explore** → select datasource **Prometheus**.
2. Run this query to confirm health-checker metrics are being scraped:
   ```
   healthchecker_node_ready
   ```
3. Navigate to **Dashboards → Browse → Kubernetes / Compute Resources / Cluster**
   to see the full cluster resource view.

### 9.4 Prometheus targets

```bash
# Port-forward Prometheus
kubectl port-forward -n monitoring svc/monitoring-kube-prometheus-prometheus 9090:9090 &
open http://localhost:9090/targets
```

Look for a `health-checker` job — it should show state `UP`.

### 9.5 GratitudeApp via ingress

```bash
# Get the NLB external hostname
NLB=$(kubectl get svc -n ingress-nginx ingress-nginx-controller \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
echo "App URL: http://$NLB"

# Quick smoke test
curl -I "http://$NLB"
# Expected: HTTP/1.1 200 OK
```

Open `http://$NLB` in a browser to use the GratitudeApp frontend.

---

## 10. Teardown

Run this when you have finished your demo or screenshots to stop all AWS charges.

**Expected time: 10–15 minutes.**

```bash
./k8s-health-checker/scripts/99-teardown.sh
```

What the script does:

```bash
# 1. Remove Helm releases
helm uninstall monitoring -n monitoring
helm uninstall ingress-nginx -n ingress-nginx

# 2. Delete health-checker resources
kubectl delete -f k8s-health-checker/deploy/healthchecker/deployment.yaml
kubectl delete -f k8s-health-checker/deploy/healthchecker/rbac.yaml

# 3. Delete all GratitudeApp Kubernetes resources (in reverse dependency order)
kubectl delete -f k8s-health-checker/gratitude-k8s/ingress-service.yml
# ... (all manifests in gratitude-k8s/)

# 4. Delete the EKS cluster + VPC (this also removes EC2, NAT gateway, NLB)
eksctl delete cluster -f k8s-health-checker/eksctl/cluster.yaml
```

### Post-teardown checklist

After the script completes, confirm in the AWS Console that:

- [ ] **EKS** → Clusters → `gratitude-health-cluster` is gone
- [ ] **EC2** → Instances → no `gratitude-health-worker` instances
- [ ] **EC2** → Load Balancers → NLB for ingress-nginx is gone
- [ ] **VPC** → NAT Gateways → deleted
- [ ] **EBS** → Volumes → no orphaned gp3 volumes
- [ ] **ECR** → `gratitude-health-checker` repo still exists (no charge unless images stored, first 500 MB/month free)

> If eksctl fails partway through, open **CloudFormation** in the AWS Console,
> find stacks named `eksctl-gratitude-health-cluster-*`, and delete them manually.

---

## Sprint 1 Deliverables Checklist

- [ ] EKS cluster provisioned (`eksctl create cluster`)
- [ ] `kubectl get nodes` shows 2 × `Ready` t3.medium nodes
- [ ] GratitudeApp 9 microservices + PostgreSQL running (`kubectl get pods -n default`)
- [ ] GratitudeApp reachable via the ingress NLB URL in a browser
- [ ] Health-checker image pushed to ECR
- [ ] Health-checker pod running (`kubectl get pods -n default -l component=health-checker`)
- [ ] `/healthz` returns `{"status":"ok"}`
- [ ] `/api/nodes`, `/api/pods`, `/api/deployments`, `/api/summary` return valid JSON
- [ ] `/metrics` returns Prometheus-format lines (node ready, pod phase, deployment replicas)
- [ ] Prometheus, Grafana, and Alertmanager pods running in `monitoring` namespace
- [ ] `health-checker` job shows `UP` in Prometheus targets (`/targets`)
- [ ] Grafana login works and `healthchecker_node_ready` metric is visible in Explore
