# GratitudeApp — Kubernetes Cluster Health Checker and Auto-Healing

This project hosts **GratitudeApp** (a 9-service MERN/gRPC
microservices app) on Amazon EKS, and builds an automated **health
monitoring and self-healing tool** around it. The health-checker
watches GratitudeApp's nodes, pods, and deployments, detects and
recovers from common failure modes (failed pods, unresponsive nodes,
resource imbalance), sends real-time alerts to Slack, and exposes a
Grafana dashboard for live and historical visibility. AWS Fault
Injection Simulator (FIS) is used to deliberately trigger failures so
the self-healing behavior can be demonstrated end-to-end.

## Problem Statement

Manually monitoring and remediating Kubernetes clusters is
time-consuming and error-prone, especially for small DevOps teams
running multi-service applications. This project automates detection
and recovery of common issues (failed pods, unresponsive nodes,
resource pressure) for GratitudeApp's microservices, reducing downtime
and manual toil while keeping the team informed via alerts and a
dashboard.

## Project Goals

1. **Automated health monitoring** — track node health, pod statuses,
   and resource utilization for GratitudeApp's services.
2. **Self-healing actions** — restart failed pods, reschedule
   workloads, and trigger scaling events when needed.
3. **Real-time alerts and notifications** — inform the team of
   critical issues requiring manual intervention.
4. **Web dashboard** — show real-time health status, historical data,
   and auto-healing logs for transparency and traceability.

## The Hosted Application: GratitudeApp

GratitudeApp is a journaling app with mood tracking, AI-assisted
entries, and stats — built as 9 microservices:

| Service | Role | Port |
|---|---|---|
| `client` | React frontend | 3000 |
| `api-gateway` | Routes requests to backend services | 5000 |
| `server-main` | Core server (auth, etc.) | 5001 |
| `entries-service` | gRPC service for journal entries | 50051 |
| `moods-api` | REST API for moods | 5002 |
| `moods-service` | gRPC service for moods | 50052 |
| `stats-api` | REST API for stats | 5003 |
| `stats-service` | gRPC service for stats | 50053 |
| `files-service` | File upload/download (S3) | 5004 |
| `postgres` | Database | 5432 |

These run as-is using the existing Docker Hub images
(`prashantdey/merndemoapp:*`) referenced in `gratitude-k8s/`.

## Tools & Technologies

| Tool | Purpose |
|---|---|
| Terraform | Provision EKS cluster, VPC, EBS CSI driver, ingress-nginx |
| Amazon EKS | Managed Kubernetes cluster hosting GratitudeApp + health-checker |
| Python (FastAPI) | Health-checker API, monitoring, and self-healing logic |
| Kubernetes Python client | Interact with and manage cluster resources |
| Prometheus | Metrics collection from the cluster and health-checker |
| Grafana | Visualization / dashboard |
| Alertmanager | Routes alerts to Slack |
| AWS FIS (Fault Injection Simulator) | Deliberately injects failures to test self-healing |
| Docker + Amazon ECR | Containerize and store the health-checker image |

## Project Structure

```
k8s-health-checker/
├── healthchecker-app/         # Python/FastAPI health-checker application
│   ├── main.py                  # FastAPI app & API routes
│   ├── monitor.py               # Polling + Prometheus metrics
│   ├── k8s_client.py            # Kubernetes API client helpers
│   ├── requirements.txt
│   └── Dockerfile
├── gratitude-k8s/              # GratitudeApp's Kubernetes manifests (as provided)
│   ├── *-deployment.yml
│   ├── *-cluster-ip-service.yml
│   ├── database-secret.yml
│   ├── openai-api-secret.yml
│   ├── storageclass-gp3-default.yml
│   ├── ingress-service.yml
│   └── postgres-migrate-job.yml
├── chaos/                       # AWS FIS chaos-testing templates (for Sprint 3)
│   ├── fis-template.json
│   ├── rbac.yml
│   ├── fis-sa-cluster-admin.yml
│   └── fis-experiement-cluster-admin.yml
├── terraform/                   # Infrastructure as Code for EKS
│   ├── versions.tf
│   ├── variables.tf
│   ├── vpc.tf
│   ├── eks.tf                    # EKS + OIDC + EBS CSI driver addon
│   ├── ingress-nginx.tf          # ingress-nginx via Helm
│   ├── outputs.tf
│   └── terraform.tfvars.example
├── deploy/
│   ├── healthchecker/
│   │   ├── rbac.yaml             # health-checker ServiceAccount + ClusterRole
│   │   └── deployment.yaml       # health-checker Deployment + Service
│   └── prometheus/
│       └── prometheus-values.yaml  # Helm values for kube-prometheus-stack
├── scripts/
│   ├── 00-build-and-push-healthchecker.sh
│   ├── 01-provision-eks.sh
│   ├── 02-deploy-gratitudeapp.sh
│   ├── 03-deploy-monitoring.sh
│   └── 99-teardown.sh
├── docs/
│   └── SECRETS.md
├── .gitignore
└── README.md
```

## Prerequisites

- AWS account + AWS CLI configured (`aws configure`)
- Terraform >= 1.5
- `kubectl`
- `helm` 3.x
- Docker (for the health-checker image only — GratitudeApp uses
  existing Docker Hub images)
- Python 3.12 (for local development of the health-checker)

## Cost Notes

This project runs on a small, short-lived EKS cluster:

- EKS control plane: ~$0.10/hour (~$72/month if left running)
- 2x t3.medium worker nodes: ~$0.083/hour combined
- Single NAT gateway (not one per AZ)
- ingress-nginx NLB: small hourly + per-GB cost while running
- Prometheus retention set to 3 days, modest resource requests

**Run `scripts/99-teardown.sh` after your demo/screenshots to avoid
ongoing charges.** A typical end-to-end demo (provision → deploy →
test → screenshot → destroy) costs roughly **$5-15** depending on how
long the cluster stays up and how long the NLB runs.

## Known Limitations (Sprint 1)

- `files-service` S3/IRSA is **not configured yet**. The pod may run
  but S3 upload/download calls will fail until an IAM role + service
  account are set up (see the original `README.md` in the GratitudeApp
  source for the IRSA steps — this can be added in a later sprint if
  needed).
- `openai-api-secret.yml` contains a placeholder key. AI-assisted
  journal features will not work until a real OpenAI key is set (see
  `docs/SECRETS.md`).

---

## Sprint-by-Sprint Progress

### Sprint 1: Project Setup and Kubernetes Cluster Access ✅

**Goal:** Establish a foundation for the project by setting up the
necessary environment, tools, and access to Kubernetes resources, and
get GratitudeApp running on EKS.

**What was done:**

1. **Project structure and repository initialized.**
   The repo is organized into: `healthchecker-app/` (the Python/
   FastAPI health-checker service we're building), `gratitude-k8s/`
   (the existing GratitudeApp Kubernetes manifests, used as-is),
   `chaos/` (AWS FIS templates for fault injection, used in Sprint 3),
   `terraform/` (EKS infrastructure as code), `deploy/` (manifests and
   Helm values for the health-checker and Prometheus stack), and
   `scripts/` (numbered, ordered automation scripts).

2. **Kubernetes cluster access configured via Terraform on EKS.**
   `terraform/` defines:
   - `vpc.tf` — a VPC with 2 public and 2 private subnets across 2
     AZs, using a **single NAT gateway** to minimize cost.
   - `eks.tf` — an EKS cluster (`module "eks"`) with one managed node
     group of **2x t3.medium** nodes (min 1, max 3 — headroom for
     Sprint 4's scaling demo), an **OIDC provider** (`enable_irsa =
     true`, needed for IRSA-based access such as the EBS CSI driver
     now and files-service-sa / FIS later), and the **aws-ebs-csi-driver
     addon** (required by GratitudeApp's `gp3` StorageClass and
     Postgres PVC).
   - `ingress-nginx.tf` — installs the `ingress-nginx` controller via
     Helm (matching GratitudeApp's `ingressClassName: nginx`), exposed
     via an AWS Network Load Balancer.
   - `variables.tf` / `terraform.tfvars.example` — all sizing and
     naming is parameterized.
   - `outputs.tf` — exposes the cluster name, endpoint, OIDC provider
     ARN, and a ready-to-run `aws eks update-kubeconfig` command.

3. **GratitudeApp deployed using its existing manifests and images.**
   `gratitude-k8s/` contains the original manifests from the
   GratitudeApp repo, applied in dependency order by
   `scripts/02-deploy-gratitudeapp.sh`: StorageClass → secrets/config →
   Postgres (PVC + Deployment + Service) → backend microservices
   (api-gateway, entries, moods-api/service, stats-api/service,
   files-service, server-main) → frontend client → ingress → one-time
   DB migration job. All services use the existing
   `prashantdey/merndemoapp:*` images from Docker Hub — no rebuilding
   needed for Sprint 1.

4. **Basic API access to Kubernetes resources, via the health-checker.**
   `deploy/healthchecker/rbac.yaml` defines a `health-checker`
   ServiceAccount (in the `default` namespace, alongside GratitudeApp)
   with a ClusterRole granting read access to nodes/pods/services/
   events, and update access to deployments/replicasets/HPAs for
   self-healing in later sprints.

   `healthchecker-app/` is a small **FastAPI** service:
   - `k8s_client.py` wraps the official Kubernetes Python client,
     using in-cluster config (via the `health-checker` ServiceAccount)
     or falling back to local kubeconfig for development.
   - `monitor.py` polls nodes, pods, and deployments in the `default`
     namespace every 15 seconds and updates Prometheus gauges
     (`healthchecker_node_ready`, `healthchecker_pod_restarts_total`,
     `healthchecker_pod_phase_running`,
     `healthchecker_deployment_available_replicas`, etc.).
   - `main.py` exposes `/healthz`, `/metrics` (Prometheus format),
     `/api/nodes`, `/api/pods`, `/api/deployments`, and `/api/summary`
     — proving the app can authenticate to and query the Kubernetes
     API for GratitudeApp's resources.
   - `Dockerfile` packages the app as a small Python container image.

5. **Prometheus installed and configured for Kubernetes.**
   `deploy/prometheus/prometheus-values.yaml` configures the
   `kube-prometheus-stack` Helm chart (Prometheus + Grafana +
   Alertmanager) with conservative resource requests, 3-day retention,
   `gp3` storage for Prometheus data, and an `additionalScrapeConfigs`
   entry that scrapes the health-checker's `/metrics` endpoint via its
   pod annotations. This lays the groundwork for Sprint 2 (dashboards),
   Sprint 5 (Alertmanager → Slack), and Sprint 6 (Grafana dashboard).

**How to run Sprint 1 end-to-end:**

```bash
# 1. Provision the EKS cluster (VPC + EKS + node group + EBS CSI + ingress-nginx)
./scripts/01-provision-eks.sh

# 2. Review/update secrets (see docs/SECRETS.md)
#    - gratitude-k8s/database-secret.yml
#    - gratitude-k8s/openai-api-secret.yml

# 3. Deploy GratitudeApp using its existing Docker Hub images
./scripts/02-deploy-gratitudeapp.sh

# 4. Build the health-checker image and push it to ECR
./scripts/00-build-and-push-healthchecker.sh
# -> copy the printed image URI into deploy/healthchecker/deployment.yaml's
#    `image:` field, replacing <YOUR_ECR_OR_DOCKERHUB_IMAGE>

# 5. Deploy the health-checker + Prometheus/Grafana/Alertmanager stack
./scripts/03-deploy-monitoring.sh

# 6. Verify everything
kubectl get pods
kubectl get ingress

# Health-checker API:
kubectl port-forward -n default svc/health-checker-cluster-ip-service 8000:8000 &
curl http://localhost:8000/api/summary

# GratitudeApp (via ingress NLB) — get the external hostname:
kubectl get svc -n ingress-nginx ingress-nginx-controller

# Grafana:
kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80 &
# open http://localhost:3000 (admin / changeme)

# 7. When done with screenshots/demo, tear everything down
./scripts/99-teardown.sh
```

**Deliverable:** Terraform-provisioned EKS cluster on AWS (with EBS
CSI driver, OIDC, and ingress-nginx), GratitudeApp's 9 microservices +
Postgres running and reachable via ingress, RBAC configured for the
health-checker ServiceAccount, a FastAPI health-checker deployed to the
cluster that successfully lists GratitudeApp's nodes/pods/deployments
via the Kubernetes API, and a running Prometheus/Grafana/Alertmanager
stack in the `monitoring` namespace.

---

### Sprint 2: Health Monitoring Module (Node & Pod Checks) ⬜ Planned

**Goal:** Enable basic health checks on nodes and pods and set up
alerts for critical issues.

**Planned work:**
- Extend `monitor.py`'s checks: add per-pod readiness/condition
  detail, and per-deployment "all replicas available" status for each
  GratitudeApp service (client, api-gateway, entries, moods, stats,
  files-service, server-main, postgres).
- Add Grafana dashboards (provisioned via the Helm values'
  `dashboardsConfigMaps` or a `ConfigMap` with `grafana_dashboard:
  "1"` label) visualizing node/pod health and GratitudeApp service
  availability.
- Define initial Alertmanager rules for thresholds (e.g. node
  NotReady > 2 minutes, any GratitudeApp deployment with
  available < desired replicas for > 1 minute, pod restart count >
  N).

---

### Sprint 3: Self-Healing Mechanisms (Pod Recovery) ⬜ Planned

**Goal:** Automate pod recovery processes and ensure that self-healing
actions are logged for transparency.

**Planned work:**
- Add a self-healing module to `healthchecker-app/` that detects and
  restarts/deletes unresponsive or failed GratitudeApp pods (using
  `delete` on pods owned by a Deployment, letting the ReplicaSet
  recreate them).
- Add automated cleanup for pods stuck in `CrashLoopBackOff` or
  `Evicted` states.
- **Use the existing `chaos/` AWS FIS templates** to deliberately
  inject failures (e.g. `fis-template.json` applies CPU stress to
  `server-deployment` pods) and validate that the health-checker
  detects and recovers from them — applying `chaos/rbac.yml` and the
  FIS service-account/role manifests sets up the permissions FIS needs.
- Implement structured audit logging of every healing action taken
  (what, when, why, result), exposed via a new `/api/healing-log`
  endpoint.

---

### Sprint 4: Advanced Self-Healing (Node Scaling & Resource Balancing) ⬜ Planned

**Goal:** Ensure the system can scale and balance resources
automatically, optimizing cluster performance and cost.

**Planned work:**
- Integrate the Kubernetes Cluster Autoscaler (or Karpenter) on EKS so
  the node group (min 1 / max 3, already configured in
  `terraform/variables.tf`) can scale up/down based on demand.
- Configure Horizontal Pod Autoscalers for GratitudeApp's
  higher-traffic services (e.g. `api-gateway`, `client`).
- Add resource-balancing logic to redistribute pods across nodes.
- Load-test these behaviors with a temporary load-generator
  deployment hitting the ingress endpoint, and screenshot the
  resulting scale-out/scale-in events.

---

### Sprint 5: Alerting and Notification System Integration ⬜ Planned

**Goal:** Implement a comprehensive alerting and notification system to
keep the team informed of critical events and actions.

**Planned work:**
- Add a Slack notifier module to `healthchecker-app/` using the Slack
  API (incoming webhook) for real-time notifications.
- Configure Alertmanager routing/receivers for multiple severity
  levels (info/warning/critical), pointing at the Slack webhook.
- End-to-end test alert delivery for both monitoring alerts (e.g. a
  GratitudeApp deployment going unavailable) and self-healing action
  notifications (e.g. "restarted pod X due to CrashLoopBackOff").
- Document alert setup and customization in `docs/`.

---

### Sprint 6: Web Dashboard and Project Documentation ⬜ Planned

**Goal:** Deliver a user-friendly dashboard for monitoring cluster
health and document the project for deployment in real-world
environments.

**Planned work:**
- Build out Grafana dashboards showing live health status of
  GratitudeApp's services, historical trends, and auto-healing/FIS
  experiment logs.
- Wire Prometheus metrics and alert/action history into the dashboard.
- Write full user documentation: setup, configuration, usage, and
  troubleshooting guides (building on `docs/SECRETS.md`).
- Final end-to-end testing on EKS, screenshot capture (including a
  full GratitudeApp demo via the ingress URL, Grafana dashboards, and
  a chaos-experiment-triggered self-healing event), and teardown via
  `scripts/99-teardown.sh`.

---

## Deliverables Summary

- GratitudeApp running on EKS via existing Docker Hub images
- Automated Health Monitoring Tool for GratitudeApp's Kubernetes
  resources
- Self-Healing Mechanisms for both pod and node recovery, validated
  via AWS FIS chaos experiments
- Real-Time Alerting and Notifications through Slack
- Web Dashboard (Grafana) for real-time and historical monitoring
- Comprehensive Documentation for setup, usage, and troubleshooting
- Terraform IaC for reproducible, cost-controlled EKS provisioning and
  teardown

## Evaluation Criteria

| Category | Weight |
|---|---|
| Documentation | 15% |
| Implementation | 75% |
| Cost Optimization | 10% |
