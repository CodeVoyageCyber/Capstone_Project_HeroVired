# Sprint 1 — Step-by-Step Execution Guide (Windows PowerShell)

**Goal:** Provision a production-like EKS cluster on AWS, deploy all 9 GratitudeApp
microservices, build and deploy the health-checker service, and stand up the
Prometheus / Grafana / Alertmanager monitoring stack — using Windows PowerShell
end to end.

> **Shell requirement:** All commands in this guide run in
> **Windows PowerShell 5.1** or **PowerShell 7+ (pwsh)**.
> Open PowerShell as **Administrator** for the installation steps (Section 1).
> Regular (non-admin) PowerShell is fine for everything after that.

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
11. [bash vs PowerShell Cheat Sheet](#11-bash-vs-powershell-cheat-sheet)

---

## 1. Prerequisites

> Run the installation commands below in a PowerShell window opened as
> **Administrator**. After each install, close and reopen PowerShell so the
> new tool appears in your `$PATH`.

### 1.1 winget (Windows Package Manager)

`winget` ships with Windows 11 and Windows 10 (build 1809+). Verify it is available:

```powershell
winget --version
# Expected: v1.x.x
```

If missing, install it from the Microsoft Store app **"App Installer"**.

### 1.2 AWS CLI v2

```powershell
winget install --id Amazon.AWSCLI --silent
```

Verify:

```powershell
aws --version
# Expected: aws-cli/2.x.x Python/3.x.x Windows/...
```

Configure with your IAM credentials (needs permissions for EKS, EC2, VPC, IAM, ECR):

```powershell
aws configure
# AWS Access Key ID     [None]: <your-access-key-id>
# AWS Secret Access Key [None]: <your-secret-access-key>
# Default region name   [None]: us-east-1
# Default output format [None]: json
```

Verify your identity:

```powershell
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

### 1.3 eksctl

```powershell
winget install --id Weaveworks.eksctl --silent
```

Verify:

```powershell
eksctl version
# Expected: 0.x.x
```

If `winget` does not find it, install via Chocolatey:

```powershell
# Install Chocolatey first (if not already installed — run as Administrator)
Set-ExecutionPolicy Bypass -Scope Process -Force
[System.Net.ServicePointManager]::SecurityProtocol = `
    [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
Invoke-Expression ((New-Object System.Net.WebClient).DownloadString(
    'https://community.chocolatey.org/install.ps1'))

# Then install eksctl
choco install eksctl -y
```

### 1.4 kubectl

```powershell
winget install --id Kubernetes.kubectl --silent
```

Verify:

```powershell
kubectl version --client
# Expected: Client Version: v1.x.x
```

### 1.5 Helm 3

```powershell
winget install --id Helm.Helm --silent
```

Verify:

```powershell
helm version
# Expected: version.BuildInfo{Version:"v3.x.x" ...}
```

### 1.6 Docker Desktop

```powershell
winget install --id Docker.DockerDesktop --silent
```

After installation:
1. Launch **Docker Desktop** from the Start menu.
2. Complete the setup wizard and accept the licence agreement.
3. Wait until the system-tray icon shows **"Engine running"**.

Verify:

```powershell
docker --version
docker info | Select-String "Server Version"
```

### 1.7 Python 3.12 (local health-checker development only)

```powershell
winget install --id Python.Python.3.12 --silent
```

Verify:

```powershell
python --version
# Expected: Python 3.12.x
```

### 1.8 Git

```powershell
winget install --id Git.Git --silent
```

Verify:

```powershell
git --version
```

---

## 2. Repository Setup

```powershell
# Clone the repository
git clone <your-repo-url>
Set-Location Capstone_Project_HeroVired

# Switch to the sprint1 branch
git checkout sprint1

# Confirm the project structure is intact
Get-ChildItem k8s-health-checker\
# Expected folders:
# healthchecker-app  gratitude-k8s  chaos  eksctl  deploy  scripts  docs
```

> **Note:** The `.sh` files under `scripts\` are bash scripts and cannot be
> run directly in PowerShell. This guide provides the PowerShell equivalent
> of every command inside each script — run them section by section below.

---

## 3. Provision the EKS Cluster

This creates the full AWS infrastructure: VPC, subnets, single NAT gateway,
EKS control plane, managed node group (2× t3.medium), OIDC provider, EBS CSI
driver addon, and ingress-nginx via Helm.

**Expected time: 15–20 minutes.**

### Step 3.1 — Create the EKS cluster

```powershell
eksctl create cluster -f k8s-health-checker\eksctl\cluster.yaml
```

eksctl streams progress to the terminal. When it finishes it automatically
updates `~\.kube\config` so `kubectl` is pointed at the new cluster.

### Step 3.2 — Verify cluster access

```powershell
kubectl get nodes
```

Expected output:

```
NAME                           STATUS   ROLES    AGE   VERSION
ip-192-168-x-x.ec2.internal    Ready    <none>   3m    v1.30.x
ip-192-168-x-x.ec2.internal    Ready    <none>   3m    v1.30.x
```

### Step 3.3 — Verify the EBS CSI driver

```powershell
kubectl get pods -n kube-system | Select-String "ebs-csi"
# Expected: one or more ebs-csi-* pods in Running state
```

### Step 3.4 — Add the ingress-nginx Helm repo

```powershell
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update
```

### Step 3.5 — Install ingress-nginx (AWS NLB)

```powershell
helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx `
  --namespace ingress-nginx --create-namespace `
  --set controller.service.type=LoadBalancer `
  --set "controller.service.annotations.service\.beta\.kubernetes\.io/aws-load-balancer-type=nlb" `
  --set controller.resources.requests.cpu=100m `
  --set controller.resources.requests.memory=128Mi
```

> **PowerShell note:** The backtick `` ` `` is PowerShell's line-continuation
> character (equivalent to `\` in bash). The annotation key contains dots so
> the entire `--set` value is wrapped in double quotes.

### Step 3.6 — Wait for ingress-nginx to be ready

```powershell
kubectl wait --for=condition=Ready pods --all -n ingress-nginx --timeout=180s
```

### Step 3.7 — Get the NLB external hostname

```powershell
kubectl get svc -n ingress-nginx ingress-nginx-controller
# The EXTERNAL-IP column shows the NLB hostname.
# It may show <pending> for 2-3 minutes while the NLB provisions.
```

---

## 4. Configure Secrets

Before deploying GratitudeApp, update the two secret files with real values.

### 4.1 Postgres password

The default password is `postgres` (base64: `cG9zdGdyZXM=`).
To use a custom password, generate its base64 value in PowerShell:

```powershell
$password = "your-secure-password"
$bytes    = [System.Text.Encoding]::UTF8.GetBytes($password)
[Convert]::ToBase64String($bytes)
# Example output: eW91ci1zZWN1cmUtcGFzc3dvcmQ=
```

Open the secret file in your editor:

```powershell
notepad k8s-health-checker\gratitude-k8s\database-secret.yml
# or, if VS Code is installed:
code k8s-health-checker\gratitude-k8s\database-secret.yml
```

Update the `PGPASSWORD` field with the base64 string you just generated:

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

```powershell
notepad k8s-health-checker\gratitude-k8s\openai-api-secret.yml
```

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: openai-api
type: Opaque
stringData:
  OPENAI_API_KEY: "sk-...your-real-key..."    # ← replace this
```

> Skipping the OpenAI key causes AI journal features to error, but entries,
> moods, stats, the health-checker, and monitoring all work normally.

---

## 5. Deploy GratitudeApp

Run each block in order. These are the PowerShell equivalents of
`scripts\02-deploy-gratitudeapp.sh`.

### Step 5.1 — Set a path variable

```powershell
$K8S = "k8s-health-checker\gratitude-k8s"
```

### Step 5.2 — Storage class, secrets, and config

```powershell
kubectl apply -f "$K8S\storageclass-gp3-default.yml"
kubectl apply -f "$K8S\database-secret.yml"
kubectl apply -f "$K8S\postgres-init-config.yml"
kubectl apply -f "$K8S\openai-api-secret.yml"
```

### Step 5.3 — Deploy Postgres

```powershell
kubectl apply -f "$K8S\database-persistent-volume-claim.yml"
kubectl apply -f "$K8S\postgres-deployment.yml"
kubectl apply -f "$K8S\postgres-cluster-ip-service.yml"

# Wait for Postgres before continuing
kubectl wait --for=condition=Ready pods -l component=postgres --timeout=180s
```

### Step 5.4 — Deploy backend microservices

```powershell
kubectl apply -f "$K8S\api-gateway-deployment.yml"
kubectl apply -f "$K8S\api-gateway-cluster-ip-service.yml"

kubectl apply -f "$K8S\entries-deployment.yml"
kubectl apply -f "$K8S\entries-cluster-ip-service.yml"

kubectl apply -f "$K8S\moods-api-deployment.yml"
kubectl apply -f "$K8S\moods-api-cluster-ip-service.yml"

kubectl apply -f "$K8S\moods-service-deployment.yml"
kubectl apply -f "$K8S\moods-service-cluster-ip-service.yml"

kubectl apply -f "$K8S\stats-api-deployment.yml"
kubectl apply -f "$K8S\stats-api-cluster-ip-service.yml"

kubectl apply -f "$K8S\stats-service-deployment.yml"
kubectl apply -f "$K8S\stats-service-cluster-ip-service.yml"

kubectl apply -f "$K8S\files-service-deployment.yml"
kubectl apply -f "$K8S\files-service-cluster-ip-service.yml"

kubectl apply -f "$K8S\server-deployment.yml"
kubectl apply -f "$K8S\server-cluster-ip-service.yml"
```

### Step 5.5 — Deploy the frontend client

```powershell
kubectl apply -f "$K8S\client-deployment.yml"
kubectl apply -f "$K8S\client-cluster-ip-service.yml"
kubectl apply -f "$K8S\client-service.yml"
```

### Step 5.6 — Apply ingress and run the DB migration job

```powershell
kubectl apply -f "$K8S\ingress-service.yml"
kubectl apply -f "$K8S\postgres-migrate-job.yml"
```

### Step 5.7 — Wait for all pods

```powershell
kubectl wait --for=condition=Ready pods --all -n default --timeout=300s
```

### Step 5.8 — Verify GratitudeApp

```powershell
# All pods should show 1/1 Running
kubectl get pods -n default

# Check ingress rule
kubectl get ingress -n default

# Get the NLB hostname and store it
$NLB = kubectl get svc -n ingress-nginx ingress-nginx-controller `
         -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'
Write-Host "GratitudeApp URL: http://$NLB"

# HTTP smoke test
Invoke-WebRequest -Uri "http://$NLB" -Method Head -UseBasicParsing
# Expected: StatusCode : 200
```

Expected `kubectl get pods -n default` output (all `1/1 Running`):

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

These are the PowerShell equivalents of `scripts\00-build-and-push-healthchecker.sh`.

### Step 6.1 — Set environment variables

```powershell
$env:AWS_REGION = "us-east-1"
$env:REPO_NAME  = "gratitude-health-checker"
$env:ACCOUNT_ID = aws sts get-caller-identity --query Account --output text
$env:ECR_URI    = "$($env:ACCOUNT_ID).dkr.ecr.$($env:AWS_REGION).amazonaws.com/$($env:REPO_NAME)"

Write-Host "ECR URI will be: $($env:ECR_URI)"
```

### Step 6.2 — Create the ECR repository (skip if it already exists)

```powershell
$repoCheck = aws ecr describe-repositories `
               --repository-names $env:REPO_NAME `
               --region $env:AWS_REGION 2>$null

if (-not $repoCheck) {
    aws ecr create-repository `
      --repository-name $env:REPO_NAME `
      --region $env:AWS_REGION
    Write-Host "ECR repository created."
} else {
    Write-Host "ECR repository already exists — skipping creation."
}
```

### Step 6.3 — Authenticate Docker to ECR

```powershell
$loginPassword = aws ecr get-login-password --region $env:AWS_REGION
$loginPassword | docker login `
  --username AWS `
  --password-stdin "$($env:ACCOUNT_ID).dkr.ecr.$($env:AWS_REGION).amazonaws.com"
# Expected: Login Succeeded
```

### Step 6.4 — Build the Docker image

```powershell
docker build -t "$($env:REPO_NAME):latest" k8s-health-checker\healthchecker-app\
```

### Step 6.5 — Tag and push to ECR

```powershell
docker tag "$($env:REPO_NAME):latest" "$($env:ECR_URI):latest"
docker push "$($env:ECR_URI):latest"
```

Note the full image URI printed at the end — you need it in the next step:

```
123456789012.dkr.ecr.us-east-1.amazonaws.com/gratitude-health-checker:latest
```

### Step 6.6 — Verify the image is in ECR

```powershell
aws ecr list-images `
  --repository-name $env:REPO_NAME `
  --region $env:AWS_REGION
# Expected: imageTag "latest" appears in the output
```

---

## 7. Update the Deployment Manifest

Open the manifest in your editor:

```powershell
notepad k8s-health-checker\deploy\healthchecker\deployment.yaml
# or
code k8s-health-checker\deploy\healthchecker\deployment.yaml
```

Find the `image:` line and replace the placeholder with your ECR URI:

```yaml
containers:
  - name: health-checker
    image: 123456789012.dkr.ecr.us-east-1.amazonaws.com/gratitude-health-checker:latest
    # ↑ replace <YOUR_ECR_OR_DOCKERHUB_IMAGE>:latest with your actual ECR URI
```

Save and confirm the change:

```powershell
Select-String -Path k8s-health-checker\deploy\healthchecker\deployment.yaml -Pattern "image:"
# Should show your ECR URI, not the placeholder
```

---

## 8. Deploy the Health-Checker and Monitoring Stack

These are the PowerShell equivalents of `scripts\03-deploy-monitoring.sh`.

### Step 8.1 — Apply RBAC

```powershell
kubectl apply -f k8s-health-checker\deploy\healthchecker\rbac.yaml
```

### Step 8.2 — Deploy the health-checker

```powershell
kubectl apply -f k8s-health-checker\deploy\healthchecker\deployment.yaml
```

### Step 8.3 — Add the Prometheus Helm repo

```powershell
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
```

### Step 8.4 — Install kube-prometheus-stack

```powershell
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack `
  --namespace monitoring --create-namespace `
  -f k8s-health-checker\deploy\prometheus\prometheus-values.yaml
```

### Step 8.5 — Wait for pods to be ready

```powershell
# Health-checker pod
kubectl wait --for=condition=Ready pods -l component=health-checker `
  -n default --timeout=180s

# All monitoring pods (Prometheus, Grafana, Alertmanager)
kubectl wait --for=condition=Ready pods --all -n monitoring --timeout=300s
```

### Step 8.6 — Confirm status

```powershell
kubectl get pods -n default
kubectl get pods -n monitoring
```

---

## 9. Verify Everything

Port-forwards must stay running while you test. Open each one in a **separate
PowerShell window**, or run them as background jobs as shown below.

### 9.1 Start port-forwards

**Option A — separate PowerShell windows (recommended):**

```powershell
# Window 1 — health-checker
kubectl port-forward -n default svc/health-checker-cluster-ip-service 8000:8000

# Window 2 — Grafana
kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80

# Window 3 — Prometheus
kubectl port-forward -n monitoring svc/monitoring-kube-prometheus-prometheus 9090:9090
```

**Option B — background jobs in the same window:**

```powershell
$hcJob   = Start-Job { kubectl port-forward -n default svc/health-checker-cluster-ip-service 8000:8000 }
$grafJob = Start-Job { kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80 }
$promJob = Start-Job { kubectl port-forward -n monitoring svc/monitoring-kube-prometheus-prometheus 9090:9090 }

# Give the tunnels a moment to establish
Start-Sleep -Seconds 3

# To stop them all later:
# Get-Job | Stop-Job; Get-Job | Remove-Job
```

### 9.2 Health-checker API

```powershell
# Liveness probe
Invoke-RestMethod http://localhost:8000/healthz
# Expected: @{status=ok}

# List cluster nodes
Invoke-RestMethod http://localhost:8000/api/nodes | ConvertTo-Json -Depth 5

# List pods in the default namespace
Invoke-RestMethod http://localhost:8000/api/pods | ConvertTo-Json -Depth 5

# List deployments
Invoke-RestMethod http://localhost:8000/api/deployments | ConvertTo-Json -Depth 5

# Full summary (also triggers an immediate Prometheus metrics refresh)
Invoke-RestMethod http://localhost:8000/api/summary | ConvertTo-Json -Depth 10

# Raw Prometheus metrics
(Invoke-WebRequest http://localhost:8000/metrics -UseBasicParsing).Content
# Expected lines:
# healthchecker_node_ready{node="ip-..."} 1.0
# healthchecker_pod_phase_running{...} 1.0
# healthchecker_deployment_available_replicas{...} 1.0
```

Filter only the health-checker metric names:

```powershell
$raw = (Invoke-WebRequest http://localhost:8000/metrics -UseBasicParsing).Content
$raw -split "`n" |
    Where-Object { $_ -match "^healthchecker" } |
    ForEach-Object { ($_ -split '\{')[0] } |
    Sort-Object -Unique
```

Expected output:

```
healthchecker_deployment_available_replicas
healthchecker_deployment_desired_replicas
healthchecker_node_ready
healthchecker_pod_phase_running
healthchecker_pod_restarts_total
```

### 9.3 Grafana dashboard

```powershell
Start-Process "http://localhost:3000"
# Username: admin
# Password: changeme
```

Once logged in:
1. Go to **Explore** → select datasource **Prometheus**.
2. Run: `healthchecker_node_ready` — should return data for both nodes.
3. Go to **Dashboards → Browse → Kubernetes / Compute Resources / Cluster**
   for the full cluster resource view.

### 9.4 Prometheus targets

```powershell
Start-Process "http://localhost:9090/targets"
# Look for job="health-checker" showing state: UP
```

### 9.5 GratitudeApp via ingress

```powershell
$NLB = kubectl get svc -n ingress-nginx ingress-nginx-controller `
         -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'

Write-Host "App URL: http://$NLB"
Start-Process "http://$NLB"

# HTTP smoke test
Invoke-WebRequest -Uri "http://$NLB" -Method Head -UseBasicParsing
# Expected: StatusCode : 200
```

---

## 10. Teardown

Run this when you have finished your demo or screenshots to stop all AWS charges.

**Expected time: 10–15 minutes.**

### Step 10.1 — Remove Helm releases

```powershell
helm uninstall monitoring  -n monitoring
helm uninstall ingress-nginx -n ingress-nginx
```

### Step 10.2 — Delete health-checker resources

```powershell
kubectl delete -f k8s-health-checker\deploy\healthchecker\deployment.yaml
kubectl delete -f k8s-health-checker\deploy\healthchecker\rbac.yaml
```

### Step 10.3 — Delete all GratitudeApp resources

```powershell
$K8S = "k8s-health-checker\gratitude-k8s"

kubectl delete -f "$K8S\ingress-service.yml"
kubectl delete -f "$K8S\client-service.yml"
kubectl delete -f "$K8S\client-cluster-ip-service.yml"
kubectl delete -f "$K8S\client-deployment.yml"
kubectl delete -f "$K8S\server-cluster-ip-service.yml"
kubectl delete -f "$K8S\server-deployment.yml"
kubectl delete -f "$K8S\files-service-cluster-ip-service.yml"
kubectl delete -f "$K8S\files-service-deployment.yml"
kubectl delete -f "$K8S\stats-service-cluster-ip-service.yml"
kubectl delete -f "$K8S\stats-service-deployment.yml"
kubectl delete -f "$K8S\stats-api-cluster-ip-service.yml"
kubectl delete -f "$K8S\stats-api-deployment.yml"
kubectl delete -f "$K8S\moods-service-cluster-ip-service.yml"
kubectl delete -f "$K8S\moods-service-deployment.yml"
kubectl delete -f "$K8S\moods-api-cluster-ip-service.yml"
kubectl delete -f "$K8S\moods-api-deployment.yml"
kubectl delete -f "$K8S\entries-cluster-ip-service.yml"
kubectl delete -f "$K8S\entries-deployment.yml"
kubectl delete -f "$K8S\api-gateway-cluster-ip-service.yml"
kubectl delete -f "$K8S\api-gateway-deployment.yml"
kubectl delete -f "$K8S\postgres-cluster-ip-service.yml"
kubectl delete -f "$K8S\postgres-deployment.yml"
kubectl delete -f "$K8S\database-persistent-volume-claim.yml"
kubectl delete -f "$K8S\openai-api-secret.yml"
kubectl delete -f "$K8S\postgres-init-config.yml"
kubectl delete -f "$K8S\database-secret.yml"
kubectl delete -f "$K8S\storageclass-gp3-default.yml"
```

### Step 10.4 — Delete the EKS cluster

```powershell
eksctl delete cluster -f k8s-health-checker\eksctl\cluster.yaml
# Deletes the VPC, subnets, NAT gateway, EC2 nodes, and NLB.
```

### Step 10.5 — Stop background port-forward jobs (if used)

```powershell
Get-Job | Stop-Job
Get-Job | Remove-Job
```

### Post-teardown checklist

Confirm in the AWS Console that the following are gone:

- [ ] **EKS** → Clusters → `gratitude-health-cluster` deleted
- [ ] **EC2** → Instances → no `gratitude-health-worker` nodes running
- [ ] **EC2** → Load Balancers → ingress-nginx NLB deleted
- [ ] **VPC** → NAT Gateways → deleted
- [ ] **EBS** → Volumes → no orphaned gp3 volumes
- [ ] **ECR** → `gratitude-health-checker` repo present (no charge under 500 MB/month free tier)

> If `eksctl delete` fails partway, open **CloudFormation** in the AWS Console,
> find stacks named `eksctl-gratitude-health-cluster-*`, and delete them manually.

---

## 11. bash vs PowerShell Cheat Sheet

| Task | bash | PowerShell |
|---|---|---|
| Set env variable | `export VAR="val"` | `$env:VAR = "val"` |
| Read env variable | `echo $VAR` | `Write-Host $env:VAR` |
| base64 encode | `echo -n "pass" \| base64` | `[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("pass"))` |
| HTTP GET (JSON) | `curl http://...` | `Invoke-RestMethod http://...` |
| HTTP HEAD check | `curl -I http://...` | `Invoke-WebRequest -Uri http://... -Method Head -UseBasicParsing` |
| Open browser | `open http://...` | `Start-Process "http://..."` |
| Grep output | `cmd \| grep "pat"` | `cmd \| Select-String "pat"` |
| Background process | `cmd &` | `Start-Job { cmd }` |
| Line continuation | `\` | `` ` `` (backtick) |
| Make directory | `mkdir -p dir/sub` | `New-Item -ItemType Directory -Force dir\sub` |
| List files | `ls` | `Get-ChildItem` or `dir` |
| Print file | `cat file.txt` | `Get-Content file.txt` |
| Delete directory | `rm -rf dir/` | `Remove-Item -Recurse -Force dir\` |
| Find in file | `grep "x" file` | `Select-String -Path file -Pattern "x"` |
| Multi-line string | `$(cat <<'EOF' ... EOF)` | `@" ... "@ ` (here-string) |
| Stop background job | `kill %1` | `Stop-Job $job; Remove-Job $job` |

---

## Sprint 1 Deliverables Checklist

- [ ] All tools installed and verified (`aws`, `eksctl`, `kubectl`, `helm`, `docker`, `python`, `git`)
- [ ] `aws sts get-caller-identity` returns your account ID
- [ ] `eksctl create cluster` completes without errors (~15-20 min)
- [ ] `kubectl get nodes` shows 2 × `Ready` t3.medium nodes
- [ ] GratitudeApp 9 microservices + PostgreSQL running (`kubectl get pods -n default`)
- [ ] `Invoke-WebRequest -Uri "http://$NLB"` returns `StatusCode 200`
- [ ] Health-checker image built and pushed to ECR (`aws ecr list-images`)
- [ ] `deployment.yaml` updated with the ECR image URI (no placeholder remaining)
- [ ] Health-checker pod running (`kubectl get pods -n default -l component=health-checker`)
- [ ] `Invoke-RestMethod http://localhost:8000/healthz` returns `status: ok`
- [ ] `/api/nodes`, `/api/pods`, `/api/deployments`, `/api/summary` return valid JSON
- [ ] Prometheus, Grafana, Alertmanager pods all `Running` in `monitoring` namespace
- [ ] `health-checker` job shows `UP` on the Prometheus `/targets` page
- [ ] Grafana login works and `healthchecker_node_ready` metric is visible in Explore
