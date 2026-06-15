# Kubernetes Cluster Health Checker and Auto-Healing

An automated health monitoring and self-healing tool for Kubernetes
clusters, running on Amazon EKS. It watches node and pod health,
automatically recovers from common failure modes (failed pods,
unresponsive nodes, resource imbalance), sends real-time alerts to
Slack/Teams, and exposes a web dashboard for live and historical
visibility.

## Problem Statement

Manually monitoring and remediating Kubernetes clusters is
time-consuming and error-prone, especially for small DevOps teams
running large clusters. This project automates detection and recovery
of common issues (failed pods, unresponsive nodes, resource pressure)
to reduce downtime and manual toil, while keeping the team informed via
alerts and a dashboard.

## Project Goals

1. **Automated health monitoring** — track node health, pod statuses,
   and resource utilization.
2. **Self-healing actions** — restart failed pods, reschedule
   workloads, and trigger scaling events when needed.
3. **Real-time alerts and notifications** — inform the team of
   critical issues requiring manual intervention.
4. **Web dashboard** — show real-time health status, historical data,
   and auto-healing logs for transparency and traceability.

## Tools & Technologies

| Tool | Purpose |
|---|---|
| Terraform | Provision EKS cluster, VPC, and node groups |
| Amazon EKS | Managed Kubernetes cluster |
| Python (FastAPI) | Health-checker API and self-healing logic |
| Kubernetes Python client | Interact with and manage cluster resources |
| Prometheus | Metrics collection from the cluster |
| Grafana | Visualization / dashboard |
| Alertmanager | Routes alerts to Slack/Teams |
| Slack API | Notifications to the DevOps team |
| Docker + Amazon ECR | Containerize and store the application image |

## Project Structure

```
k8s-health-checker/
├── app/                       # Python/FastAPI health-checker application
│   ├── main.py                 # FastAPI app & API routes
│   ├── k8s_client.py            # Kubernetes API client helpers
│   ├── requirements.txt
│   └── Dockerfile
├── terraform/                  # Infrastructure as Code for EKS
│   ├── versions.tf
│   ├── variables.tf
│   ├── vpc.tf
│   ├── eks.tf
│   ├── outputs.tf
│   └── terraform.tfvars.example
├── deploy/
│   ├── k8s/
│   │   ├── rbac.yaml            # ServiceAccount, ClusterRole, binding
│   │   └── deployment.yaml      # App Deployment + Service
│   └── prometheus/
│       └── prometheus-values.yaml  # Helm values for kube-prometheus-stack
├── scripts/
│   ├── 00-build-and-push.sh     # Build & push app image to ECR
│   ├── 01-provision-eks.sh      # terraform apply + configure kubectl
│   ├── 02-deploy-app.sh         # Deploy RBAC, app, and monitoring stack
│   └── 99-teardown.sh           # Destroy everything (avoid ongoing costs)
├── docs/
├── .gitignore
└── README.md
```

## Prerequisites

- AWS account + AWS CLI configured (`aws configure`)
- Terraform >= 1.5
- `kubectl`
- `helm` 3.x
- Docker
- Python 3.12 (for local development of the app)

## Cost Notes

This project is designed to run on a small, short-lived EKS cluster:

- EKS control plane: ~$0.10/hour (~$72/month if left running)
- 2x t3.medium worker nodes: ~$0.083/hour combined
- Single NAT gateway (not one per AZ) to reduce networking cost
- Prometheus retention set to 3 days, modest resource requests

**Run `scripts/99-teardown.sh` after your demo/screenshots to avoid
ongoing charges.** A typical end-to-end demo (provision → deploy →
test → screenshot → destroy) costs roughly **$3-10** depending on how
long the cluster stays up.

---

## Sprint-by-Sprint Progress

### Sprint 1: Project Setup and Kubernetes Cluster Access ✅

**Goal:** Establish a foundation for the project by setting up the
necessary environment, tools, and access to Kubernetes resources.

**What was done:**

1. **Project structure and repository initialized.**
   The repo is organized into four top-level areas: `app/` (the
   Python/FastAPI health-checker service), `terraform/` (EKS
   infrastructure as code), `deploy/` (Kubernetes manifests and Helm
   values), and `scripts/` (numbered, ordered automation scripts that
   take the project from zero to a running demo and back down to
   zero). This separation lets infrastructure, application code, and
   Kubernetes configuration evolve independently.

2. **Kubernetes cluster access configured via Terraform on EKS.**
   `terraform/` defines:
   - `vpc.tf` — a VPC with 2 public and 2 private subnets across 2
     AZs, using a **single NAT gateway** to minimize cost, with the
     subnet tags EKS needs for load balancer discovery.
   - `eks.tf` — an EKS cluster (`module "eks"`, using the
     `terraform-aws-modules/eks/aws` module) with one managed node
     group of **2x t3.medium** nodes (min 1, max 3 — the max headroom
     is used later for Sprint 4's scaling demo).
   - `variables.tf` / `terraform.tfvars.example` — all sizing and
     naming is parameterized so instance types, node counts, and
     region can be changed without editing the module code.
   - `outputs.tf` — exposes the cluster name, endpoint, and a ready-to
     -run `aws eks update-kubeconfig` command.

3. **Basic API access to Kubernetes resources.**
   `deploy/k8s/rbac.yaml` defines a `health-checker` namespace,
   ServiceAccount, ClusterRole, and ClusterRoleBinding with the
   minimum permissions needed across all sprints: read/list/watch/
   delete on pods, nodes, services, events; update on deployments/
   replicasets; and create/update on HorizontalPodAutoscalers.

   The application itself (`app/`) is a small **FastAPI** service:
   - `k8s_client.py` wraps the official Kubernetes Python client. It
     loads in-cluster config automatically when running as a pod (via
     the `health-checker` ServiceAccount), and falls back to the
     local kubeconfig for development.
   - `main.py` exposes `/healthz` (liveness), `/api/nodes` (lists all
     cluster nodes and their Ready status), and `/api/pods` (lists
     pods, optionally filtered by namespace). These two endpoints are
     the Sprint 1 proof that the app can authenticate to and query the
     Kubernetes API.
   - `Dockerfile` packages the app as a small Python container image.

4. **Prometheus installed and configured for Kubernetes.**
   `deploy/prometheus/prometheus-values.yaml` configures the
   `kube-prometheus-stack` Helm chart (Prometheus + Grafana +
   Alertmanager bundled together) with conservative resource requests,
   3-day retention, and a small persistent volume — sized to fit
   comfortably alongside the app on 2x t3.medium nodes. This single
   chart also lays the groundwork for Sprint 2 (metrics), Sprint 5
   (Alertmanager), and Sprint 6 (Grafana dashboard).

**How to run Sprint 1 end-to-end:**

```bash
# 1. Provision the EKS cluster (VPC + EKS + node group via Terraform)
./scripts/01-provision-eks.sh

# 2. Build the app image and push it to ECR
./scripts/00-build-and-push.sh
# -> copy the printed image URI into deploy/k8s/deployment.yaml's
#    `image:` field, replacing <YOUR_ECR_REPO_URI>

# 3. Deploy RBAC, the app, and the Prometheus/Grafana/Alertmanager stack
./scripts/02-deploy-app.sh

# 4. Verify API access
kubectl port-forward -n health-checker svc/health-checker 8000:80 &
curl http://localhost:8000/api/nodes
curl http://localhost:8000/api/pods

# 5. Access Grafana (bundled with Prometheus stack)
kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80 &
# open http://localhost:3000 (admin / changeme)

# 6. When done with screenshots/demo, tear everything down
./scripts/99-teardown.sh
```

**Deliverable:** Terraform-provisioned EKS cluster on AWS, RBAC
configured for the health-checker ServiceAccount, a FastAPI app
deployed to the cluster that successfully lists nodes and pods via the
Kubernetes API, and a running Prometheus/Grafana/Alertmanager stack in
the `monitoring` namespace.

---

### Sprint 2: Health Monitoring Module (Node & Pod Checks) ⬜ Planned

**Goal:** Enable basic health checks on nodes and pods and set up
alerts for critical issues.

**Planned work:**
- Extend `app/` with a monitoring module that polls node conditions
  (Ready, MemoryPressure, DiskPressure, etc.) and pod statuses
  (Running, Pending, CrashLoopBackOff, etc.) via the Kubernetes API.
- Expose custom Prometheus metrics (e.g.
  `healthchecker_node_ready`, `healthchecker_pod_restarts_total`) via
  a `/metrics` endpoint (using `prometheus-client`) and configure a
  `ServiceMonitor` so Prometheus scrapes them.
- Add Grafana dashboards visualizing node/pod health and resource
  usage (CPU, memory).
- Define initial Alertmanager rules for thresholds (e.g. node
  NotReady > 2 minutes, pod restart count > N).

---

### Sprint 3: Self-Healing Mechanisms (Pod Recovery) ⬜ Planned

**Goal:** Automate pod recovery processes and ensure that self-healing
actions are logged for transparency.

**Planned work:**
- Add a self-healing module to `app/` that detects and restarts/
  reschedules unresponsive or failed pods using the Kubernetes API.
- Add automated cleanup for pods stuck in `CrashLoopBackOff` or
  `Evicted` states.
- Validate self-healing behavior in a staging namespace on the EKS
  cluster.
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
- Configure Horizontal Pod Autoscalers for high-demand workloads.
- Add resource-balancing logic to redistribute pods across nodes.
- Load-test these behaviors with a temporary load-generator
  deployment, and screenshot the resulting scale-out/scale-in events.

---

### Sprint 5: Alerting and Notification System Integration ⬜ Planned

**Goal:** Implement a comprehensive alerting and notification system to
keep the team informed of critical events and actions.

**Planned work:**
- Add a Slack (and optionally Teams) notifier module to `app/` using
  the Slack API for real-time notifications.
- Configure Alertmanager routing/receivers for multiple severity
  levels (info/warning/critical), pointing at the Slack webhook.
- End-to-end test alert delivery for both monitoring alerts and
  self-healing action notifications.
- Document alert setup and customization in `docs/`.

---

### Sprint 6: Web Dashboard and Project Documentation ⬜ Planned

**Goal:** Deliver a user-friendly dashboard for monitoring cluster
health and document the project for deployment in real-world
environments.

**Planned work:**
- Build out Grafana dashboards (or a lightweight custom web UI in
  `app/`) showing live health status, historical trends, and
  auto-healing logs.
- Wire Prometheus metrics and alert/action history into the dashboard.
- Write full user documentation: setup, configuration, usage, and
  troubleshooting guides.
- Final end-to-end testing on EKS, screenshot capture, and teardown via
  `scripts/99-teardown.sh`.

---

## Deliverables Summary

- Automated Health Monitoring Tool for Kubernetes clusters (on EKS)
- Self-Healing Mechanisms for both pod and node recovery
- Real-Time Alerting and Notifications through Slack/Teams
- Web Dashboard for real-time and historical monitoring
- Comprehensive Documentation for setup, usage, and troubleshooting
- Terraform IaC for reproducible, cost-controlled EKS provisioning and
  teardown

## Evaluation Criteria

| Category | Weight |
|---|---|
| Documentation | 15% |
| Implementation | 75% |
| Cost Optimization | 10% |
