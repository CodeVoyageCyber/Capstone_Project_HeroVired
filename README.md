# GratitudeApp — Kubernetes Cluster Health Checker and Auto-Healing

## Architecture

![Architecture Diagram](docs/diagrams/architecture.svg)

All six sprints were first implemented on **Minikube**, then transferred to
**Amazon EKS**. The application, health-checker, and monitoring stack share the
same Kubernetes design; ingress, persistent storage, image distribution, and
AWS integrations differ between environments. See [Implementation and migration](#implementation-and-migration-minikube-to-eks)
for the sprint runbooks and environment differences.

The diagram shows the implemented Kubernetes stack and its deployment journey.
Solid arrows show application, monitoring, and control flows; dashed arrows show
optional integrations or environment-specific dependencies. The editable diagram
source is [architecture.svg](docs/diagrams/architecture.svg).

GratitudeApp comprises nine application microservices plus PostgreSQL. A Python /
FastAPI health-checker monitors nodes, pods, and deployments, deletes qualifying
unhealthy pods so Kubernetes can recreate them, records healing actions, and
reports pod distribution across nodes. Prometheus collects metrics, Grafana
provides dashboards, and Alertmanager and the health-checker provide separate
notification paths to Slack when configured.

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
(`prashantdey/merndemoapp:*`) referenced in `k8s-health-checker/gratitude-k8s/`.

## Tools & Technologies

| Tool | Purpose |
|---|---|
| Minikube | Local implementation and validation of all six sprints |
| eksctl | Provision EKS cluster, VPC, EBS CSI driver addon, OIDC |
| Amazon EKS | Managed Kubernetes cluster hosting GratitudeApp + health-checker |
| Python (FastAPI) | Health-checker API, monitoring, and self-healing logic |
| Kubernetes Python client | Interact with and manage cluster resources |
| Prometheus | Metrics collection from the cluster and health-checker |
| Grafana | Visualization / dashboard |
| Alertmanager | Routes alerts to Slack |
| AWS FIS (Fault Injection Simulator) | Deliberately injects failures to test self-healing |
| Docker + Amazon ECR | Containerize and store the health-checker image |

## Project Structure

```text
.
├── README.md
├── Project_details.txt                # Original project requirements
├── GratitudeApp-main/                 # Hosted application source
│   ├── client/                         # React frontend
│   └── k8s/                            # Application manifests in source project
├── k8s-health-checker/                 # Health-checker and deployment automation
│   ├── healthchecker-app/              # FastAPI, monitor, healer, balancer, Slack notifier
│   ├── gratitude-k8s/                  # Application manifests used by deployment scripts
│   ├── chaos/                         # AWS FIS templates and RBAC
│   ├── eksctl/cluster.yaml             # Cluster config used by provisioning script
│   ├── deploy/
│   │   ├── healthchecker/              # Deployment, Service, RBAC
│   │   ├── prometheus/                 # kube-prometheus-stack Helm values
│   │   ├── grafana/                    # Sprint 2 and Sprint 6 dashboards
│   │   ├── alerts/                     # PrometheusRules and Alertmanager config
│   │   └── autoscaling/                # HPAs, load generator, optional node autoscaler
│   ├── scripts/                       # Build/push, provision, deploy, teardown
│   └── docs/SECRETS.md
├── k8s-local/                         # Minikube storage and health-checker overrides
├── docs/
│   ├── minikube_implementation/        # Local setup and sprint implementation guides
│   ├── eks_migration/                  # Migration overview and EKS sprint runbooks
│   ├── diagrams/architecture.svg       # Current architecture diagram
│   ├── alerting-and-notifications.md
│   └── user-guide.md
├── cluster.yaml                       # Separate root-level cluster configuration
└── scripts/99-teardown.sh              # Root-level teardown helper
```

Run the numbered deployment scripts from `k8s-health-checker/`. Its
`eksctl/cluster.yaml` is the configuration used by the provisioning script;
the root-level `cluster.yaml` is a separate copy and currently differs.


## Prerequisites

- Minikube for the local implementation (see the [local setup guide](docs/minikube_implementation/Readme_Local.md))
- AWS account + AWS CLI configured (`aws configure`)
- `eksctl`
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

**From `k8s-health-checker/`, run `scripts/99-teardown.sh` after your demo/screenshots to avoid
ongoing charges.** A typical end-to-end demo (provision → deploy →
test → screenshot → destroy) costs roughly **$5-15** depending on how
long the cluster stays up and how long the NLB runs.

## Configuration and Implementation Limits

- `files-service` S3/IRSA is **not configured yet**. The pod may run
  but S3 upload/download calls will fail until an IAM role + service
  account are set up (see the original `README.md` in the GratitudeApp
  source for the IRSA steps — this can be added in a later sprint if
  needed).
- `openai-api-secret.yml` contains a placeholder key. AI-assisted
  journal features will not work until a real OpenAI key is set (see
  [secret configuration guide](k8s-health-checker/docs/SECRETS.md)).

---

## Sprint-by-Sprint Progress: Minikube Implementation

All six sprints were first implemented on a local Minikube cluster. The
summaries below describe that local work; the following migration section
explains how the stack was transferred to Amazon EKS. Paths are relative to
the repository root.

### Sprint 1: Project Setup and Kubernetes Cluster Access

**Goal:** Establish local Kubernetes access and deploy GratitudeApp with the
health-checker and monitoring foundation.

**Implementation on Minikube:**

- Started Minikube with the Docker driver and enabled the nginx ingress and
  metrics-server addons.
- Used `k8s-local/storageclass-local.yaml` to provide a StorageClass named
  `gp3` backed by Minikube hostPath storage, replacing the AWS EBS provisioner.
- Deployed the manifests in `k8s-health-checker/gratitude-k8s/` in dependency
  order: secrets and configuration, PostgreSQL with its PVC, backend services,
  frontend, ingress, and the database migration job. Application containers
  used the existing `prashantdey/merndemoapp:*` Docker Hub images.
- Built the health-checker image inside Minikube's Docker environment and used
  the local deployment and service overrides in `k8s-local/`.
- Applied the health-checker ServiceAccount and RBAC, then verified node, pod,
  deployment, summary, and metrics endpoints against the local Kubernetes API.
- Installed Prometheus, Grafana, and Alertmanager in the `monitoring` namespace
  using `kube-prometheus-stack`. Accessed the application through local ingress
  and internal monitoring services through port-forwarding.

**Result:** A local application and monitoring stack ready for the remaining
sprints, without requiring EKS provisioning or an ECR image push.

**Reference:** [Minikube deployment and verification guide](docs/minikube_implementation/Readme_Local.md).

### Sprint 2: Health Monitoring Module (Node & Pod Checks)

**Goal:** Expand node and pod visibility and detect degraded application services.

**Implementation on Minikube:**

- Extended pod API responses with readiness and condition details, and added
  `healthchecker_pod_ready` and
  `healthchecker_deployment_all_replicas_available` metrics.
- Rebuilt and redeployed the local health-checker image with the monitoring
  changes.
- Added `k8s-health-checker/deploy/grafana/node-pod-health-dashboard.yaml` as
  a dashboard ConfigMap discovered by Grafana's sidecar.
- Added `k8s-health-checker/deploy/alerts/gratitudeapp-alerts.yaml` for
  node, pod, and deployment health alerts.
- Documented checks for Prometheus scraping, dashboard visibility, and the
  alert lifecycle using a temporary deployment scale-down followed by restore.

**Result:** Local readiness metrics, a node/pod health dashboard, and health
alert rules alongside the original cluster inventory endpoints.

**Reference:** [Sprint 2 local implementation and verification](docs/minikube_implementation/Readme_Local_Sprint2.md).

### Sprint 3: Self-Healing Mechanisms (Pod Recovery)

**Goal:** Recover unhealthy application pods and record the recovery actions.

**Implementation on Minikube:**

- Added `healer.py` and integrated healing scans with the monitoring poller.
  The recovery logic deletes qualifying unhealthy workload pods so their
  Kubernetes controllers can recreate them, and cleans up evicted pods.
- Added a per-workload cooldown to limit repeated healing actions.
- Exposed structured action history through `/api/healing-log`, on-demand
  scans through `/api/heal`, and action counts through
  `healthchecker_healing_actions_total`.
- Used local crash-loop and evicted-pod scenarios to exercise recovery and
  inspect the audit log and metrics. The guide also describes a local CPU
  stress simulation.
- Prepared AWS FIS templates and permissions for the later EKS environment;
  AWS FIS itself was not available on Minikube.

**Result:** Pod recovery and an observable healing audit trail on the local
cluster, with AWS-specific chaos testing covered by the EKS runbook.

**Reference:** [Sprint 3 local recovery and failure-testing guide](docs/minikube_implementation/Readme_Local_Sprint3.md).

### Sprint 4: Advanced Self-Healing (Node Scaling & Resource Balancing)

**Goal:** Add workload autoscaling configuration and visibility into resource
capacity and pod distribution.

**Implementation on Minikube:**

- Added workload CPU/memory requests and limits and CPU-based HPA definitions
  for the API gateway, client, and server deployments, using metrics-server.
- Added `balancer.py` to report per-node pod counts, allocatable CPU, workload
  distribution, and a cluster balance ratio through metrics and
  `/api/node-balancing`.
- Added the load-generator manifest and documented load testing and HPA
  scale-out/scale-in checks on the local cluster.
- Kept AWS node-group scaling separate: the Cluster Autoscaler manifest is an
  EKS integration requiring cloud configuration, rather than a local
  Minikube node-scaling mechanism.

**Result:** Local HPA configuration and resource distribution reporting.
The balance module reports distribution; it does not actively move pods.
The current checked-in HPAs cap replicas at **1**, so reproducing scale-out
requires increasing their maximum replica counts.

**Reference:** [Sprint 4 local autoscaling and resource reporting guide](docs/minikube_implementation/Readme_Local_Sprint4.md).

### Sprint 5: Alerting and Notification System Integration

**Goal:** Notify the team about degraded health and automated recovery actions.

**Implementation on Minikube:**

- Added `slack_notifier.py` for formatted notifications, including healing
  events, with mock mode when no webhook is supplied and live mode when a
  Slack incoming webhook is configured.
- Exposed `/api/notify/slack` for test messages and `/api/notifications` for
  recent notification history.
- Added severity-based Alertmanager routing and receiver configuration under
  `k8s-health-checker/deploy/alerts/`, alongside the Prometheus alert rules.
- Documented test notifications, healing notifications, and monitoring-alert
  delivery checks. Live Slack delivery depends on configuring the webhook
  separately for the health-checker and Alertmanager.

**Result:** Two notification paths: direct health-checker action notifications
and Prometheus alerts routed through Alertmanager.

**Reference:** [Sprint 5 local notification guide](docs/minikube_implementation/Readme_Local_Sprint5.md)
and [alerting configuration](docs/alerting-and-notifications.md).

### Sprint 6: Web Dashboard and Project Documentation

**Goal:** Bring the monitoring features together in a full observability
view and document operation of the local stack.

**Implementation on Minikube:**

- Added `k8s-health-checker/deploy/grafana/sprint6-full-dashboard.yaml` as a
  sidecar-discovered Grafana dashboard ConfigMap, alongside the Sprint 2
  dashboard.
- Combined node readiness, pod health, replica availability, healing counts,
  historical trends, HPA state, active alerts, and cluster balance metrics
  in the full observability dashboard.
- Documented dashboard access through port-forwarding and final checks of
  the application, health-checker API, Prometheus targets, alerts, and
  notification behavior.
- Added user and alerting guides covering setup, configuration, operation,
  troubleshooting, and local cleanup.

**Result:** A documented local monitoring and self-healing stack covering all
six sprints, forming the baseline subsequently transferred to EKS.

**Reference:** [Sprint 6 local dashboard and final verification guide](docs/minikube_implementation/Readme_Local_Sprint6.md)
and [user guide](docs/user-guide.md).

---

## Implementation and Migration: Minikube to EKS

The sprint section above describes the local implementation. **All six sprints
were implemented first on Minikube and then transferred to EKS**. The references
below connect each local implementation to its EKS deployment runbook.

### Phase 1: Implement all sprints on Minikube

The [local deployment guide](docs/minikube_implementation/Readme_Local.md)
sets up GratitudeApp, the health-checker, and `kube-prometheus-stack`. Local
overrides in `k8s-local/` use Minikube hostPath storage and a locally built
health-checker image. Subsequent sprints add readiness metrics, healing,
resource distribution reports, notifications, and Grafana dashboards.

### Phase 2: Transfer the stack to Amazon EKS

[EKS transfer snapshot (Word document)](docs/eks_migration/EKS_Capstone.docx)

The [Minikube-to-EKS migration guide](docs/eks_migration/minikube-to-eks-migration.md)
describes the environment changes. The EKS runbooks below carry each sprint's
features onto the managed cluster, using the existing Docker Hub application
images and an ECR-hosted health-checker image. This is a redeployment of the
stack; the guides do not document copying local PostgreSQL volume data to EBS.

| Sprint | Implemented capability | Minikube implementation | EKS transfer and verification |
|---|---|---|---|
| 1 | Application, PostgreSQL, Kubernetes API access, RBAC, monitoring foundation | [Local setup](docs/minikube_implementation/Readme_Local.md) | [EKS Sprint 1](docs/eks_migration/readme_eks_sprint1.md) |
| 2 | Pod readiness, deployment availability, health dashboard, alert rules | [Local Sprint 2](docs/minikube_implementation/Readme_Local_Sprint2.md) | [EKS Sprint 2](docs/eks_migration/readme_eks_sprint2.md) |
| 3 | Pod recovery, cooldown, healing audit log and metrics; failure testing | [Local Sprint 3](docs/minikube_implementation/Readme_Local_Sprint3.md) | [EKS Sprint 3](docs/eks_migration/readme_eks_sprint3.md) |
| 4 | CPU-based HPAs, load testing, pod distribution and capacity reports | [Local Sprint 4](docs/minikube_implementation/Readme_Local_Sprint4.md) | [EKS Sprint 4](docs/eks_migration/readme_eks_sprint4.md) |
| 5 | Health-checker notifications and severity-based Alertmanager routing | [Local Sprint 5](docs/minikube_implementation/Readme_Local_Sprint5.md) | [EKS Sprint 5](docs/eks_migration/readme_eks_sprint5.md) |
| 6 | Full observability dashboard, documentation and end-to-end checks | [Local Sprint 6](docs/minikube_implementation/Readme_Local_Sprint6.md) | [EKS Sprint 6](docs/eks_migration/readme_eks_sprint6.md) |

### What changed between environments

| Component | Minikube | Amazon EKS |
|---|---|---|
| Cluster | Local Minikube cluster | eksctl-managed EKS cluster and EC2 managed node group |
| Application entry | nginx ingress addon; local access / tunnel | AWS NLB → ingress-nginx → ClusterIP services |
| Persistent storage | `k8s-local/storageclass-local.yaml`: class named `gp3`, backed by `k8s.io/minikube-hostpath` | EBS CSI-backed `gp3` storage for PostgreSQL and Prometheus |
| Health-checker image | Local Docker build and local deployment override | Build/push to ECR; EKS deployment pulls the image |
| Application images | Existing `prashantdey/merndemoapp:*` images | Same Docker Hub images |
| Observability | Prometheus, Grafana, Alertmanager in `monitoring` | Same stack, dashboard ConfigMaps and PrometheusRules reapplied |
| Internal service access | Port-forward health-checker, Grafana and Prometheus | Same port-forward approach; application ingress is public via NLB |
| Failure testing | Local failure scenarios and recovery checks | Recovery checks plus optional AWS FIS experiment |
| Node scaling | Local capacity; HPA depends on metrics-server | Optional Cluster Autoscaler after IAM, ASG tags and compatible image are configured |

The implemented behavior has these configuration boundaries:

- `healer.py` handles pod recovery; Kubernetes controllers recreate deleted
  workload pods. Node readiness is monitored, rather than repaired directly.
- `balancer.py` reports distribution and capacity metrics; it does not actively
  move pods. The checked-in HPAs currently have both minimum and maximum replicas
  set to **1**, so scale-out demonstrations require increasing the maximum.
- AWS FIS is an optional EKS-only exercise. Cluster Autoscaler is also optional
  and its checked-in manifest needs configuration before use.
- Slack supports mock and live delivery. The current EKS health-checker manifest
  references the `health-checker-slack` Secret; supply it with an empty webhook
  for mock mode or a real webhook for live delivery. Alertmanager requires its
  own receiver configuration. See [alerting and notifications](docs/alerting-and-notifications.md).
- S3 file operations depend on files-service IAM/IRSA configuration; AI-assisted
  entries require a valid OpenAI key. See [secrets](k8s-health-checker/docs/SECRETS.md).

For setup, operation and troubleshooting, start with the [user guide](docs/user-guide.md)
and follow the environment-specific sprint runbooks in order. Some older guides
use paths relative to `k8s-health-checker/`; the project tree above shows their
current locations from the repository root.

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
- eksctl-based cluster config for reproducible, cost-controlled EKS
  provisioning and teardown

## Evaluation Criteria

| Category | Weight |
|---|---|
| Documentation | 15% |
| Implementation | 75% |
| Cost Optimization | 10% |
