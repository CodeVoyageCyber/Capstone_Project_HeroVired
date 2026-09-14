# Local Deployment Guide — minikube

Run the full GratitudeApp + Health Checker + Monitoring stack on your laptop
using minikube. No AWS account required.

> **What works locally:** GratitudeApp (9 services), health-checker API,
> Prometheus, Grafana, Alertmanager, PrometheusRules, Grafana dashboards.
>
> **What does NOT work locally:** AWS FIS chaos testing, S3 file uploads
> (files-service starts but upload/download calls fail), ECR (replaced by
> local Docker build).

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Start minikube](#2-start-minikube)
3. [Create the Local StorageClass Override](#3-create-the-local-storageclass-override)
4. [Create the Local Health-Checker Deployment Override](#4-create-the-local-health-checker-deployment-override)
5. [Configure Secrets](#5-configure-secrets)
6. [Deploy GratitudeApp](#6-deploy-gratitudeapp)
7. [Build the Health-Checker Image](#7-build-the-health-checker-image)
8. [Deploy the Health-Checker and Monitoring Stack](#8-deploy-the-health-checker-and-monitoring-stack)
9. [Access the Application](#9-access-the-application)
10. [Verify Everything](#10-verify-everything)
11. [Teardown](#11-teardown)

---

## 1. Prerequisites

Install the following tools before starting.

### 1.1 minikube

```bash
# macOS
brew install minikube

# Linux
curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
sudo install minikube-linux-amd64 /usr/local/bin/minikube

# Windows (run as Administrator)
winget install Kubernetes.minikube

# Verify
minikube version
# Expected: minikube version: v1.x.x
```

### 1.2 kubectl

```bash
# macOS
brew install kubectl

# Linux
curl -LO "https://dl.k8s.io/release/$(curl -sL https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl && sudo mv kubectl /usr/local/bin/

# Windows
winget install Kubernetes.kubectl

# Verify
kubectl version --client
```

### 1.3 Helm 3

```bash
# macOS / Linux
brew install helm

# Windows
winget install Helm.Helm

# Verify
helm version
```

### 1.4 Docker

Docker Desktop (Mac/Windows) or Docker Engine (Linux) must be running before
you start minikube.

```bash
docker --version
docker info | grep "Server Version"
```

---

## 2. Start minikube

minikube needs enough resources to run 9 GratitudeApp services + PostgreSQL +
the health-checker + Prometheus/Grafana/Alertmanager simultaneously.

```bash
minikube start \
  --cpus=4 \
  --memory=6144 \
  --disk-size=20g \
  --driver=docker
```

> **Minimum specs:** 4 CPUs and 6 GB RAM allocated to minikube. The monitoring
> stack alone (Prometheus 512 Mi + Grafana 256 Mi + Alertmanager 128 Mi) uses
> ~1 GB, and the 9 GratitudeApp services + Postgres use another ~1.5 GB.
>
> <img width="2114" height="950" alt="image" src="https://github.com/user-attachments/assets/5af54af6-80ab-45a8-b40d-773061dff428" />


### Enable required addons

```bash
# nginx ingress controller (replaces the AWS NLB from EKS)
minikube addons enable ingress

# metrics-server (used by Kubernetes resource dashboards in Grafana)
minikube addons enable metrics-server
```

### Verify minikube is healthy

```bash
minikube status
# Expected:
# minikube: Running
# cluster: Running
# kubectl: Correctly Configured

kubectl get nodes
# Expected: 1 node in Ready state
# NAME       STATUS   ROLES           AGE   VERSION
# minikube   Ready    control-plane   1m    v1.30.x

kubectl get pods -n ingress-nginx
# Expected: ingress-nginx-controller-xxx pod in Running state
```
<img width="1142" height="220" alt="image" src="https://github.com/user-attachments/assets/07ba5a14-7b56-4f64-9c74-55676fe1accc" />
<img width="1180" height="106" alt="image" src="https://github.com/user-attachments/assets/612d96e2-1fe7-4917-9cf0-a160ae1c07d7" />

<img width="1432" height="160" alt="image" src="https://github.com/user-attachments/assets/0b46d510-a732-4d5b-b90c-0819141ed85d" />
---

## 3. Create the Local StorageClass Override

The existing `storageclass-gp3-default.yml` uses the AWS EBS CSI provisioner
(`ebs.csi.aws.com`) which does not exist in minikube. You must apply a local
replacement that defines a `gp3` StorageClass backed by minikube's hostpath
provisioner. This means all PVC manifests work unchanged.

### Step 3.1 — Create the local overrides directory

```bash
mkdir -p k8s-local
```

### Step 3.2 — Create the local StorageClass file

```bash
cat > k8s-local/storageclass-local.yaml << 'EOF'
# Local minikube replacement for storageclass-gp3-default.yml.
# Uses minikube's built-in hostpath provisioner instead of AWS EBS CSI.
# volumeBindingMode must be Immediate (hostpath does not support WaitForFirstConsumer).
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: gp3
  annotations:
    storageclass.kubernetes.io/is-default-class: "true"
provisioner: k8s.io/minikube-hostpath
reclaimPolicy: Delete
volumeBindingMode: Immediate
allowVolumeExpansion: false
EOF
```

### Step 3.3 — Apply it (do NOT apply the original storageclass-gp3-default.yml)

```bash
kubectl apply -f k8s-local/storageclass-local.yaml
# Expected: storageclass.storage.k8s.io/gp3 created

kubectl get storageclass
# Expected: gp3 is listed as the default (*)
# NAME            PROVISIONER                RECLAIMPOLICY   VOLUMEBINDINGMODE   AGE
# gp3 (default)   k8s.io/minikube-hostpath   Delete          Immediate           5s
# standard        k8s.io/minikube-hostpath   Delete          Immediate           2m
```
<img width="1560" height="228" alt="image" src="https://github.com/user-attachments/assets/dc0087c6-5c83-48e0-957d-885082815877" />

---

## 4. Create the Local Health-Checker Deployment Override

The original `deploy/healthchecker/deployment.yaml` references an ECR image
URI. Locally, you will build the image directly into minikube's Docker daemon
and reference it with `imagePullPolicy: Never` so Kubernetes never tries to
pull from a remote registry.

### Step 4.1 — Create the local deployment file

```bash
cat > k8s-local/healthchecker-deployment-local.yaml << 'EOF'
# Local minikube override for deploy/healthchecker/deployment.yaml.
# Uses the locally-built image with imagePullPolicy: Never.
apiVersion: apps/v1
kind: Deployment
metadata:
  name: health-checker-deployment
  namespace: default
  labels:
    component: health-checker
spec:
  replicas: 1
  selector:
    matchLabels:
      component: health-checker
  template:
    metadata:
      labels:
        component: health-checker
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8000"
        prometheus.io/path: "/metrics"
    spec:
      serviceAccountName: health-checker
      containers:
        - name: health-checker
          image: gratitude-health-checker:latest
          imagePullPolicy: Never
          ports:
            - containerPort: 8000
          env:
            - name: TARGET_NAMESPACE
              value: "default"
          resources:
            requests:
              cpu: 50m
              memory: 128Mi
            limits:
              cpu: 200m
              memory: 256Mi
          readinessProbe:
            httpGet:
              path: /healthz
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /healthz
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 20
---
apiVersion: v1
kind: Service
metadata:
  name: health-checker-cluster-ip-service
  namespace: default
  labels:
    component: health-checker
spec:
  selector:
    component: health-checker
  ports:
    - port: 8000
      targetPort: 8000
  type: ClusterIP
EOF
```
<img width="1560" height="228" alt="image" src="https://github.com/user-attachments/assets/4ce01756-4d73-4631-8105-9d8a4b299abc" />

---

## 5. Configure Secrets

### 5.1 Postgres password

The default password `postgres` (base64: `cG9zdGdyZXM=`) is fine for local
development. To use a custom password:

```bash
echo -n "your-local-password" | base64
# e.g.: eW91ci1sb2NhbC1wYXNzd29yZA==
```

Open the secret file and update `PGPASSWORD` if needed:

```bash
# Default value is already set — only edit if you want a different password
cat k8s-health-checker/gratitude-k8s/database-secret.yml
```

### 5.2 OpenAI API key (optional)

AI journal features will not work without a real key, but everything else
(entries, moods, stats, health-checker, monitoring) works without it.

```bash
# Optional — set a real key if you want AI features
# Edit k8s-health-checker/gratitude-k8s/openai-api-secret.yml
# and replace the placeholder with your key
```

---

## 6. Deploy GratitudeApp

Set the path variable, then apply manifests in dependency order.

```bash
K8S="k8s-health-checker/gratitude-k8s"

# Step 1 — Local StorageClass (already applied in Step 3 — skip the original)
# DO NOT run: kubectl apply -f $K8S/storageclass-gp3-default.yml
# It was replaced by k8s-local/storageclass-local.yaml above.

# Step 2 — Secrets and config
kubectl apply -f $K8S/database-secret.yml
kubectl apply -f $K8S/postgres-init-config.yml
kubectl apply -f $K8S/openai-api-secret.yml

# Step 3 — Postgres (PVC → Deployment → Service)
kubectl apply -f $K8S/database-persistent-volume-claim.yml
kubectl apply -f $K8S/postgres-deployment.yml
kubectl apply -f $K8S/postgres-cluster-ip-service.yml

echo "Waiting for Postgres to be ready..."
kubectl wait --for=condition=Ready pods -l component=postgres --timeout=180s

# Step 4 — Backend microservices
kubectl apply -f $K8S/api-gateway-deployment.yml
kubectl apply -f $K8S/api-gateway-cluster-ip-service.yml
kubectl apply -f $K8S/entries-deployment.yml
kubectl apply -f $K8S/entries-cluster-ip-service.yml
kubectl apply -f $K8S/moods-api-deployment.yml
kubectl apply -f $K8S/moods-api-cluster-ip-service.yml
kubectl apply -f $K8S/moods-service-deployment.yml
kubectl apply -f $K8S/moods-service-cluster-ip-service.yml
kubectl apply -f $K8S/stats-api-deployment.yml
kubectl apply -f $K8S/stats-api-cluster-ip-service.yml
kubectl apply -f $K8S/stats-service-deployment.yml
kubectl apply -f $K8S/stats-service-cluster-ip-service.yml
kubectl apply -f $K8S/files-service-deployment.yml
kubectl apply -f $K8S/files-service-cluster-ip-service.yml
kubectl apply -f $K8S/server-deployment.yml
kubectl apply -f $K8S/server-cluster-ip-service.yml

# Step 5 — Frontend client
kubectl apply -f $K8S/client-deployment.yml
kubectl apply -f $K8S/client-cluster-ip-service.yml
kubectl apply -f $K8S/client-service.yml

# Step 6 — Ingress (uses minikube's nginx addon — no changes needed)
kubectl apply -f $K8S/ingress-service.yml

# Step 7 — One-time DB migration job
kubectl apply -f $K8S/postgres-migrate-job.yml

# Step 8 — Wait for all GratitudeApp pods
echo "Waiting for all GratitudeApp pods (this can take 3-5 minutes on first pull)..."
kubectl wait --for=condition=Ready pods --all -n default --timeout=300s
```
<img width="1754" height="260" alt="image" src="https://github.com/user-attachments/assets/d01f71be-397f-4142-a43b-1726faa989b5" />
<img width="2206" height="350" alt="image" src="https://github.com/user-attachments/assets/f82db870-0383-4555-8956-9ce541c580c0" />
<img width="2202" height="1176" alt="image" src="https://github.com/user-attachments/assets/07fa2799-533d-4058-8893-c792cd188d99" />
<img width="1918" height="272" alt="image" src="https://github.com/user-attachments/assets/77f08f99-55c9-4186-9256-f2287f9fe8e2" />
<img width="1824" height="204" alt="image" src="https://github.com/user-attachments/assets/d10d16d9-98e2-403f-afed-609940717419" />

### Verify GratitudeApp pods

```bash
kubectl get pods -n default
```

Expected output (all `1/1 Running`):

```
NAME                                    READY   STATUS    RESTARTS   AGE
api-gateway-deployment-xxx              1/1     Running   0          3m
client-deployment-xxx                   1/1     Running   0          2m
entries-deployment-xxx                  1/1     Running   0          2m
files-service-deployment-xxx            1/1     Running   0          2m
moods-api-deployment-xxx                1/1     Running   0          2m
moods-service-deployment-xxx            1/1     Running   0          2m
postgres-deployment-xxx                 1/1     Running   0          5m
server-deployment-xxx                   1/1     Running   0          2m
stats-api-deployment-xxx                1/1     Running   0          2m
stats-service-deployment-xxx            1/1     Running   0          2m
```
<img width="1600" height="516" alt="image" src="https://github.com/user-attachments/assets/bcb4238a-04cb-46d6-a250-0a11730b1c05" />

---

## 7. Build the Health-Checker Image

minikube runs its own internal Docker daemon, separate from your host machine's
Docker. To make the locally-built image available to Kubernetes pods without
pushing to a registry, point your shell's Docker client at minikube's daemon,
then build.

### Step 7.1 — Point Docker at minikube's daemon

```bash
eval $(minikube docker-env)
# Your shell is now talking to minikube's internal Docker daemon.
# Any image you build here is immediately available to minikube pods.

# Verify — you should see minikube's internal images
docker images | grep k8s
```
<img width="2454" height="582" alt="image" src="https://github.com/user-attachments/assets/6fe8e75d-0d76-431d-a7c7-c6c2cf2f745f" />

### Step 7.2 — Build the image

```bash
docker build -t gratitude-health-checker:latest \
  k8s-health-checker/healthchecker-app/
```
<img width="2182" height="1228" alt="image" src="https://github.com/user-attachments/assets/a53d24a7-3526-445d-a91c-5b63d8145666" />

### Step 7.3 — Confirm the image is visible inside minikube

```bash
minikube image ls | grep gratitude-health-checker
# Expected: docker.io/library/gratitude-health-checker:latest
```
<img width="2808" height="1420" alt="image" src="https://github.com/user-attachments/assets/b3c1353f-b70b-4b4e-994f-26b42a9e6a0d" />

### Step 7.4 — Reset Docker to your host daemon (optional)

```bash
# Run this after building if you want to use your regular Docker again
eval $(minikube docker-env --unset)
```

> **Alternative approach (without eval):** Build on your host and load:
> ```bash
> docker build -t gratitude-health-checker:latest k8s-health-checker/healthchecker-app/
> minikube image load gratitude-health-checker:latest
> ```

---

## 8. Deploy the Health-Checker and Monitoring Stack

### Step 8.1 — Apply RBAC

```bash
kubectl apply -f k8s-health-checker/deploy/healthchecker/rbac.yaml
```

### Step 8.2 — Deploy the health-checker using the local image override

```bash
# Use the local override (NOT the original deployment.yaml which has imagePullPolicy: Always + ECR URI)
kubectl apply -f k8s-local/healthchecker-deployment-local.yaml
```

### Step 8.3 — Wait for the health-checker pod

```bash
kubectl wait --for=condition=Ready pods -l component=health-checker \
  -n default --timeout=120s

kubectl get pods -n default -l component=health-checker
# Expected: 1/1 Running
```

### Step 8.4 — Add Prometheus Helm repo

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
```
<img width="2184" height="248" alt="image" src="https://github.com/user-attachments/assets/b4ef1f9d-e29c-4a93-871f-098238ed937e" />

### Step 8.5 — Install kube-prometheus-stack

```bash
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  -f k8s-health-checker/deploy/prometheus/prometheus-values.yaml
```

> The Prometheus values file requests a `gp3` PVC for storage. Since we
> created a local `gp3` StorageClass backed by hostpath in Step 3, this
> will be provisioned automatically with no AWS dependency.

<img width="2892" height="1030" alt="image" src="https://github.com/user-attachments/assets/294becdf-4c18-4e0f-a98f-aac8b8fcfcdd" />

### Step 8.6 — Wait for the monitoring stack

```bash
echo "Waiting for Prometheus, Grafana, and Alertmanager (3-5 minutes)..."
kubectl wait --for=condition=Ready pods --all -n monitoring --timeout=300s
```

<img width="2150" height="260" alt="image" src="https://github.com/user-attachments/assets/baaa5e15-b4e0-4b26-a0b4-0ad5da864c37" />

### Step 8.7 — Confirm all pods are running

```bash
kubectl get pods -n default
kubectl get pods -n monitoring
kubectl get pods -n ingress-nginx
```

<img width="1926" height="930" alt="image" src="https://github.com/user-attachments/assets/9463bd97-47bb-420f-8784-11e680200851" />

---

## 9. Access the Application

Unlike EKS (which uses an AWS NLB), minikube accesses services via its own IP
address or through port-forwarding.

### 9.1 Get the minikube IP

```bash
minikube ip
# e.g.: 192.168.49.2
```

### 9.2 Access GratitudeApp via the ingress

```bash
# The ingress controller listens on minikube's IP on port 80
MINIKUBE_IP=$(minikube ip)
echo "GratitudeApp URL: http://$MINIKUBE_IP"

# Quick smoke test
curl -I "http://$MINIKUBE_IP"
# Expected: HTTP/1.1 200 OK

# Open in browser
open "http://$MINIKUBE_IP"
```

> On some systems, minikube may not route traffic to its IP automatically.
> If `curl` times out, use `minikube tunnel` instead:
> ```bash
> # Run in a separate terminal — keep it open while testing
> minikube tunnel
> # Then access via http://localhost (the tunnel maps port 80)
> ```

<img width="1590" height="376" alt="image" src="https://github.com/user-attachments/assets/0135a110-2aeb-454d-86eb-f077a62b95c5" />

<img width="2694" height="1864" alt="image" src="https://github.com/user-attachments/assets/3c16beda-7e58-4d34-948e-af71dfbd78c6" />

### 9.3 Port-forward the health-checker API

```bash
# Open in a separate terminal or run in the background
kubectl port-forward -n default svc/health-checker-cluster-ip-service 8000:8000 &

# Test immediately
curl http://localhost:8000/healthz
# Expected: {"status":"ok"}
```

<img width="2210" height="186" alt="image" src="https://github.com/user-attachments/assets/a5513b0b-40dd-4377-985e-a8f23e762ae4" />

<img width="353" height="106" alt="image" src="https://github.com/user-attachments/assets/229829c8-1e79-413b-a9f5-cc96fb1606b1" />

### 9.4 Port-forward Grafana

```bash
kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80 &
open http://localhost:3000
# Username: admin   Password: changeme
```

<img width="2026" height="138" alt="image" src="https://github.com/user-attachments/assets/3031e774-203f-4fdc-aa57-0308ed3afc92" />

<img width="3412" height="1776" alt="image" src="https://github.com/user-attachments/assets/a192f919-5cb7-44ba-a250-ae76cf00ac4b" />

### 9.5 Port-forward Prometheus

```bash
kubectl port-forward -n monitoring \
  svc/monitoring-kube-prometheus-prometheus 9090:9090 &
open http://localhost:9090
```

<img width="1700" height="178" alt="image" src="https://github.com/user-attachments/assets/576e7fd0-1947-4b62-9e8c-f89e714559cd" />

---

## 10. Verify Everything

### 10.1 Health-checker API endpoints

```bash
# Liveness
curl http://localhost:8000/healthz
# {"status":"ok"}

# Nodes
curl http://localhost:8000/api/nodes | python3 -m json.tool
# {"nodes": [{"name": "minikube", "ready": "True"}]}

# Pods in the default namespace
curl http://localhost:8000/api/pods | python3 -m json.tool

# Deployments
curl http://localhost:8000/api/deployments | python3 -m json.tool

# Full summary
curl http://localhost:8000/api/summary | python3 -m json.tool

# Prometheus metrics
curl http://localhost:8000/metrics | grep "^healthchecker" | \
  awk -F'{' '{print $1}' | sort -u
```

<img width="390" height="98" alt="image" src="https://github.com/user-attachments/assets/28480976-3b23-49f8-a6e0-6458be4ff030" />

<img width="3330" height="448" alt="image" src="https://github.com/user-attachments/assets/c51179b3-83fd-4448-b526-8cbb90c5b8f9" />

<img width="1406" height="1884" alt="image" src="https://github.com/user-attachments/assets/4c135538-74d5-49e1-84c2-ac56c5602f5f" />

<img width="3340" height="378" alt="image" src="https://github.com/user-attachments/assets/75d7438c-0a70-4cfe-a5a7-7889fa017576" />

Expected metric names:

```
healthchecker_deployment_available_replicas
healthchecker_deployment_desired_replicas
healthchecker_node_ready
healthchecker_pod_phase_running
healthchecker_pod_restarts_total
```
<img width="1752" height="1736" alt="image" src="https://github.com/user-attachments/assets/80d51ec2-d52e-4c71-9ec6-49515ba64c9e" />

### 10.2 Prometheus is scraping the health-checker

```bash
open http://localhost:9090/targets
# Look for job="health-checker" in state UP
```
<img width="3404" height="1860" alt="image" src="https://github.com/user-attachments/assets/931c8d71-135a-4d73-8f6f-ec4772afd5a2" />

Run a test query in Prometheus:

```
healthchecker_node_ready
# Expected: value 1 for node="minikube"
```

### 10.3 Grafana is connected to Prometheus

1. Open `http://localhost:3000` → log in as `admin / changeme`
2. Go to **Explore** → datasource **Prometheus**
3. Query: `healthchecker_node_ready` → should return data
<img width="2824" height="1766" alt="image" src="https://github.com/user-attachments/assets/0c72a7a1-6ae7-4d51-b825-b940344639a5" />
4. Go to **Dashboards → Browse → Kubernetes / Compute Resources / Cluster**
<img width="3406" height="1888" alt="image" src="https://github.com/user-attachments/assets/8a5acf18-235b-4936-abcf-98e4893b31e2" />

### 10.4 GratitudeApp ingress routing

```bash
MINIKUBE_IP=$(minikube ip)

# API gateway
curl "http://$MINIKUBE_IP/api/journal/"
# Expected: JSON response or auth error (not a 404)

# Frontend
curl -s -o /dev/null -w "%{http_code}" "http://$MINIKUBE_IP/"
# Expected: 200
```
<img width="819" height="184" alt="image" src="https://github.com/user-attachments/assets/53fd5f93-3667-4734-ac13-2dbe72ac48ea" />

### 10.5 PVC is bound (local storage working)

```bash
kubectl get pvc -n default
# Expected: database-persistent-volume-claim   Bound   ...   gp3

kubectl get pvc -n monitoring
# Expected: prometheus-monitoring-kube-prometheus-prometheus-0   Bound   ...   gp3
```
<img width="2214" height="384" alt="image" src="https://github.com/user-attachments/assets/d21346bc-b3ec-4139-81dc-253ff9420b6d" />

---

## 11. Teardown

### 11.1 Delete all Kubernetes resources

```bash
# Helm releases
helm uninstall monitoring -n monitoring

# Health-checker
kubectl delete -f k8s-local/healthchecker-deployment-local.yaml
kubectl delete -f k8s-health-checker/deploy/healthchecker/rbac.yaml

# GratitudeApp
K8S="k8s-health-checker/gratitude-k8s"
kubectl delete -f $K8S/ingress-service.yml
kubectl delete -f $K8S/client-service.yml
kubectl delete -f $K8S/client-cluster-ip-service.yml
kubectl delete -f $K8S/client-deployment.yml
kubectl delete -f $K8S/server-cluster-ip-service.yml
kubectl delete -f $K8S/server-deployment.yml
kubectl delete -f $K8S/files-service-cluster-ip-service.yml
kubectl delete -f $K8S/files-service-deployment.yml
kubectl delete -f $K8S/stats-service-cluster-ip-service.yml
kubectl delete -f $K8S/stats-service-deployment.yml
kubectl delete -f $K8S/stats-api-cluster-ip-service.yml
kubectl delete -f $K8S/stats-api-deployment.yml
kubectl delete -f $K8S/moods-service-cluster-ip-service.yml
kubectl delete -f $K8S/moods-service-deployment.yml
kubectl delete -f $K8S/moods-api-cluster-ip-service.yml
kubectl delete -f $K8S/moods-api-deployment.yml
kubectl delete -f $K8S/entries-cluster-ip-service.yml
kubectl delete -f $K8S/entries-deployment.yml
kubectl delete -f $K8S/api-gateway-cluster-ip-service.yml
kubectl delete -f $K8S/api-gateway-deployment.yml
kubectl delete -f $K8S/postgres-cluster-ip-service.yml
kubectl delete -f $K8S/postgres-deployment.yml
kubectl delete -f $K8S/database-persistent-volume-claim.yml
kubectl delete -f $K8S/openai-api-secret.yml
kubectl delete -f $K8S/postgres-init-config.yml
kubectl delete -f $K8S/database-secret.yml
kubectl delete -f k8s-local/storageclass-local.yaml
```

### 11.2 Stop minikube (keeps cluster state)

```bash
minikube stop
# Cluster is paused — restart with: minikube start
```
<img width="625" height="77" alt="image" src="https://github.com/user-attachments/assets/c2c52071-ca78-4fec-8f63-d117dd0c3ce5" />

### 11.3 Delete minikube entirely (wipes all data)

```bash
minikube delete
# Deletes the VM/container, all volumes, all images cached inside minikube
```

### 11.4 Stop background port-forwards

```bash
# Kill all kubectl port-forward processes
pkill -f "kubectl port-forward"
```

---

## Local vs EKS — Quick Reference

| Aspect | Local (minikube) | EKS (Sprint 1 guide) |
|---|---|---|
| Cluster start | `minikube start` (~2 min) | `eksctl create cluster` (~20 min) |
| StorageClass | `k8s.io/minikube-hostpath` | `ebs.csi.aws.com` (gp3) |
| Ingress | minikube addon (NodePort) | ingress-nginx via Helm (NLB) |
| Health-checker image | Local Docker build | ECR push |
| `imagePullPolicy` | `Never` | `Always` (default) |
| App access | `minikube ip` or port-forward | NLB external hostname |
| AWS FIS | ❌ Not available | ✅ Available |
| S3 (files upload) | ❌ Fails silently | ✅ With IRSA setup |
| Cost | Free | ~$6–7/day |
| Nodes | 1 (minikube VM) | 2 × t3.medium |

---

## Troubleshooting

### Pod stuck in `Pending`

```bash
kubectl describe pod <pod-name> -n default
# Look for "Events:" at the bottom
# Common cause: PVC not bound — check kubectl get pvc
```

If the PVC is `Pending`:

```bash
kubectl get pvc -n default
# If Pending, the StorageClass may not be applied correctly
kubectl get storageclass
# Confirm gp3 is listed with k8s.io/minikube-hostpath provisioner
```

### Health-checker pod in `ErrImageNeverPull`

This means `imagePullPolicy: Never` is set but the image is not in minikube's daemon:

```bash
# Re-run the build inside minikube's Docker daemon
eval $(minikube docker-env)
docker build -t gratitude-health-checker:latest \
  k8s-health-checker/healthchecker-app/

# Restart the pod to pick up the new image
kubectl rollout restart deployment/health-checker-deployment -n default
```

### ingress returns 404 for all routes

```bash
# Check the nginx ingress controller is running
kubectl get pods -n ingress-nginx

# Check the ingress resource was created
kubectl get ingress -n default
kubectl describe ingress ingress-service -n default

# Check minikube IP
minikube ip
```

### minikube is out of memory

```bash
# Stop and recreate with more memory
minikube stop
minikube delete
minikube start --cpus=4 --memory=8192 --disk-size=20g --driver=docker
```

### Prometheus PVC stuck in `Pending`

The Prometheus Helm chart creates its own PVC named
`prometheus-monitoring-kube-prometheus-prometheus-0`. If it's stuck, confirm
the `gp3` StorageClass with `volumeBindingMode: Immediate` was applied before
installing the Helm chart:

```bash
kubectl get storageclass gp3 -o yaml | grep volumeBindingMode
# Must be: volumeBindingMode: Immediate
# (NOT WaitForFirstConsumer — hostpath does not support it)
```

---

## Local Deployment Checklist

- [ ] `minikube status` shows all components `Running`
- [ ] `minikube addons enable ingress` — ingress pod in `Running` state
- [ ] `kubectl get storageclass` — `gp3` listed with `k8s.io/minikube-hostpath`
- [ ] `kubectl get pvc` — `database-persistent-volume-claim` is `Bound`
- [ ] All 10 GratitudeApp pods `1/1 Running` (`kubectl get pods -n default`)
- [ ] `minikube image ls | grep gratitude-health-checker` — image is present
- [ ] Health-checker pod `1/1 Running` (`-l component=health-checker`)
- [ ] `curl http://localhost:8000/healthz` returns `{"status":"ok"}`
- [ ] All 5 metric families visible at `http://localhost:8000/metrics`
- [ ] Prometheus, Grafana, Alertmanager pods `Running` in `monitoring` namespace
- [ ] `http://localhost:9090/targets` shows `health-checker` job as `UP`
- [ ] Grafana login works at `http://localhost:3000`
- [ ] `http://$(minikube ip)/` loads the GratitudeApp frontend
