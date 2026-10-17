# GratitudeApp — Kubernetes Health Checker and Auto-Healing on KinD

Build a local Kubernetes monitoring and recovery lab using **KinD (Kubernetes
in Docker)**. GratitudeApp provides the application workloads; a Python/FastAPI
health checker observes Kubernetes resources; Prometheus and Grafana provide
metrics and visibility. The six-sprint roadmap adds controlled pod recovery,
autoscaling, Slack notifications, and a final project dashboard.

**Current status:** this branch contains a detailed Sprint 1 implementation guide
and the six-sprint target architecture. The KinD deployment has not been verified
live. Sprints 2–6 are planned. Follow the guide to create the lab files and run
the implementation yourself.

## Architecture

![KinD architecture with Sprint 1–6 assignments](docs/diagrams/kind-architecture.png)

[Editable SVG](docs/diagrams/kind-architecture.svg) ·
[Architecture details and sprint mapping](docs/kind/ARCHITECTURE.md) ·
[Sprint 1 implementation guide](docs/kind/SPRINT-1.md)

The target cluster contains **one control-plane and two worker containers** inside
Docker Desktop. Three namespaces separate responsibilities:

| Namespace | Components | Responsibility |
|---|---|---|
| `gratitude` | Nine GratitudeApp services and PostgreSQL | Application traffic and persistent application data |
| `health-system` | FastAPI health checker; planned healer and audit store | Kubernetes observation and controlled remediation |
| `monitoring` | Prometheus Operator, Prometheus, Grafana, Alertmanager and exporters | Metrics collection, visualization and alert routing |

The health checker reads the Kubernetes API using a ServiceAccount with read-only
RBAC in Sprint 1. Prometheus discovers its `/metrics` endpoint through a
ServiceMonitor and also collects Kubernetes object and resource metrics. Grafana
queries Prometheus. Later sprints add scoped healing permissions and Slack delivery.

Sprint badges indicate where capabilities belong. Dashed cards and flows identify
planned extensions; components with multiple badges are installed early and
enhanced later. They are not completion indicators.

## Problem and goals

Monitoring and recovering multi-service Kubernetes applications manually makes
failures hard to detect, explain, and reproduce. This project uses a local cluster
to develop and demonstrate:

- Node, pod, service, and deployment health observation.
- Resource metrics and threshold-based alerts.
- Opt-in recovery of unhealthy Deployment-owned pods with an audit trail.
- Horizontal pod autoscaling and workload placement across workers.
- Slack notifications for critical conditions and recovery actions.
- Dashboards, repeatable failure exercises, and an operational runbook.

## Tools and prerequisites

| Tool | Role in the KinD implementation |
|---|---|
| Docker Desktop / Docker Engine | Runs Kubernetes node containers and builds application images |
| KinD | Creates and deletes the local Kubernetes cluster; loads local images |
| kubectl | Applies manifests, inspects resources, and forwards local ports |
| Helm | Installs the `kube-prometheus-stack` monitoring chart |
| Python 3.12, FastAPI, Kubernetes Python client | Implements the health-checker API and polling |
| Prometheus and Prometheus Operator | Scrapes metrics, discovers ServiceMonitors, and evaluates alert rules |
| Grafana | Explores metrics and presents dashboards |
| Alertmanager | Groups and routes alerts; Slack integration is planned for Sprint 5 |
| Metrics Server | Supplies HPA resource metrics in Sprint 4 |
| PostgreSQL and local PVCs | Store application data; monitoring also uses local persistent storage |

For the full application and monitoring stack, start with approximately **6 CPUs,
10–12 GiB RAM, and 25 GiB free disk** available to Docker. These are lab estimates;
actual requirements depend on workload and retention settings. The nodes share
these resources.

Internet access is needed to install dependencies, download charts, and pull base
images. Core journaling and monitoring do not require a cloud account. AI features
require an optional OpenAI key; Slack delivery requires a webhook when implemented.

On macOS with Homebrew installed, install the command-line tools:

```bash
brew install kind kubectl helm python@3.12
```

Install and start Docker Desktop separately, then verify:

```bash
docker info
kind version
kubectl version --client
helm version
python3.12 --version
```

Docker must report a running server before creating the cluster.

## Repository structure

```text
Capstone_Project_HeroVired/
├── README.md
├── Project_details.txt                    # Original project goals and sprint requirements
├── GratitudeApp-main/                     # Application source and Dockerfiles
│   ├── client/
│   ├── services/
│   └── protos/
├── docs/
│   ├── kind/
│   │   ├── ARCHITECTURE.md                # KinD design and sprint mapping
│   │   └── SPRINT-1.md                    # Complete step-by-step implementation guide
│   └── diagrams/
│       ├── kind-architecture.png
│       ├── kind-architecture.svg
│       ├── generate-kind-architecture.py
│       └── render-kind-architecture.py
└── k8s-health-checker/                    # Existing code and original deployment references
    ├── healthchecker-app/
    ├── gratitude-k8s/
    ├── deploy/
    ├── scripts/
    ├── eksctl/
    └── chaos/
```

The Sprint 1 guide creates a separate **`kind-lab/`** workspace as you follow its
commands. It is not a ready-made deployment directory in the current checkout:

```text
kind-lab/
├── cluster/                              # KinD configuration and node-image record
├── app/                                  # Local Dockerfiles and adapted application manifests
├── healthchecker/                        # New FastAPI source, dependencies and Dockerfile
├── k8s/                                  # Namespaces, scoped RBAC, Deployment and Service
├── monitoring/                           # Helm values, chart version and ServiceMonitor
└── evidence/                             # Validation output, ignored by Git
```

The existing deployment references include cloud-specific scripts, storage, and
permissions. The KinD guide selectively adapts application manifests; do not apply
the original directory wholesale or use its provisioning/teardown scripts for this
lab. The guide's new health checker is independent of the older implementation.

## Implement Sprint 1

Start with the [Sprint 1 guide](docs/kind/SPRINT-1.md). It includes every file and
command needed for the foundation, in this order:

1. Verify Docker and tools; confirm the `KinD` branch.
2. Create the `kind-lab/` structure and three-node cluster configuration.
3. Create the cluster, select `kind-gratitude`, and verify Ready nodes.
4. Create `gratitude`, `health-system`, and `monitoring` namespaces.
5. Write the read-only FastAPI health checker and optionally test it locally.
6. Build its Docker image and load it into the KinD node runtimes.
7. Apply scoped RBAC, then deploy the health checker and Service.
8. Build GratitudeApp images, generate local manifests, and create local secrets.
9. Deploy PostgreSQL and the application; validate a journal create/list round trip.
10. Select and record a compatible monitoring chart version, then install it.
11. Create the ServiceMonitor and verify Prometheus scraping and Grafana queries.
12. Test dynamic workload discovery and capture completion evidence.

Docker images built on the host must be loaded with `kind load docker-image`.
The guide uses local `standard` storage, namespace-scoped observation permissions,
and explicit `--context kind-gratitude` commands.

### Access the lab after deployment

These commands assume you have completed the guide and the named Services exist.
Run each port-forward in its own terminal and leave it running:

```bash
kubectl --context kind-gratitude port-forward -n health-system \
  service/healthchecker 8000:8000 --address 127.0.0.1
```

```bash
kubectl --context kind-gratitude port-forward -n monitoring \
  service/monitoring-kube-prometheus-prometheus 9090:9090 --address 127.0.0.1
```

```bash
kubectl --context kind-gratitude port-forward -n monitoring \
  service/monitoring-grafana 3000:80 --address 127.0.0.1
```

| Local URL | Purpose |
|---|---|
| `http://127.0.0.1:8000/docs` | Interactive health-checker API documentation |
| `http://127.0.0.1:8000/api/summary` | Latest nodes, pods, services, and deployment snapshot |
| `http://127.0.0.1:8000/readyz` | Freshness of Kubernetes observations |
| `http://127.0.0.1:8000/metrics` | Prometheus-format health-checker metrics |
| `http://127.0.0.1:9090` | Prometheus targets and PromQL queries |
| `http://127.0.0.1:3000` | Grafana Explore and dashboards |

The guide explains how to retrieve the generated Grafana password and how to find
Service names if your selected chart version differs. Closing a forwarding terminal
ends local access; it does not stop the cluster.

## Application workloads

GratitudeApp includes nine application services plus PostgreSQL. In this lab,
application images are built from the checked-in source and loaded into KinD.

| Component | Role | Container port |
|---|---|---|
| `client` | React frontend served by nginx | 80; Kubernetes Service exposes 3000 |
| `api-gateway` | REST entry point to journal/gRPC and AI features | 5000 |
| `server-main` | Core Express API | 5001 |
| `entries-service` | Journal entries gRPC service | 50051 |
| `moods-api` | Mood REST API | 5002 |
| `moods-service` | Mood gRPC service | 50052 |
| `stats-api` | Statistics REST API | 5003 |
| `stats-service` | Statistics gRPC service | 50053 |
| `files-service` | File upload/download API | 5004 |
| `postgres` | Application database | 5432 |

Sprint 1 verifies the journal backend directly through port-forwarding. Serving the
frontend assets alone does not configure the browser's `/api` routes. Shared
frontend/backend routing and a local S3-compatible file backend remain planned
application integration work. AI features remain optional.

## Sprint roadmap and acceptance criteria

### Sprint 1 — Project setup and Kubernetes API access

**Status: guide available; execution unverified.**

Create KinD, deploy the application baseline, implement the observer, configure
read-only RBAC, and install monitoring. Completion requires three Ready nodes,
ready application deployments, a successful journal round trip, working API
snapshots, denied write/secret permissions, an UP Prometheus target, and Grafana
queries returning custom metrics.

**Guide:** [SPRINT-1.md](docs/kind/SPRINT-1.md).

### Sprint 2 — Node and pod health monitoring

**Status: planned.**

Expand condition/readiness checks and resource visibility. Add initial Grafana
panels and custom Prometheus rules for sustained node unavailability, insufficient
replicas, and excessive restarts. Validate each condition with a controlled test
and confirm that alerts fire and resolve.

### Sprint 3 — Pod recovery and audit

**Status: planned.**

Add opt-in recovery for eligible Deployment-owned pods, including failed/evicted
pods and sustained `CrashLoopBackOff` or unready conditions. Introduce narrowly
scoped write permissions, owner validation, grace periods, cooldowns, and durable
audit records. Use isolated local failure exercises to verify detection, action,
replacement, and audit results. Kubernetes's own Deployment reconciliation already
replaces deleted pods; demonstrate what the custom controller adds.

### Sprint 4 — Autoscaling and resource balancing

**Status: planned.**

Install Metrics Server, configure CPU/resource requests and HPA, and run controlled
load tests to observe replica growth and reduction. Use topology spread and
scheduling policies to distribute new pods across workers. Scheduling policies do
not automatically rebalance every running pod; any active redistribution needs an
explicit design and test.

KinD has a fixed worker topology. Worker-capacity simulation can demonstrate
scheduling pressure and recovery, but does not provision machines or add physical
capacity. Keep this separate from the real pod autoscaling provided by HPA.

### Sprint 5 — Alerts and notifications

**Status: planned.**

Configure Alertmanager severity routes and Slack delivery. Store webhook URLs in
Secrets, integrate healing notifications explicitly, and test both firing and
resolved messages. Verify that repeated failures do not produce notification storms.

### Sprint 6 — Final dashboard, integration, and documentation

**Status: planned.**

Deliver Grafana views for service health, resource trends, alerts, and healing
activity. Make per-action audit history accessible through a suitable API or data
source. Complete browser routing and local file-storage integration, write the
runbook, and collect end-to-end evidence for deployment, failures, recovery,
scaling, and notifications.

Separate `SPRINT-2.md` through `SPRINT-6.md` implementation guides are planned;
they are not yet included in this branch.

## Validation and troubleshooting

After following the guide, inspect the lab:

```bash
kubectl --context kind-gratitude get nodes -o wide
kubectl --context kind-gratitude get pods -A
kubectl --context kind-gratitude get deployments,services,pvc -n gratitude
kubectl --context kind-gratitude logs -n health-system deployment/healthchecker --tail=50
kubectl --context kind-gratitude get events -A --sort-by=.lastTimestamp
```

With port-forwarding active:

```bash
curl -fsS http://127.0.0.1:8000/readyz
curl -fsS http://127.0.0.1:8000/api/summary | python3 -m json.tool
```

In Prometheus, check `healthchecker_collection_success` and
`healthchecker_node_ready`. An UP scrape target proves endpoint connectivity;
collection success and freshness establish whether Kubernetes observation works.

| Symptom | First check |
|---|---|
| Docker unavailable | Start the engine and verify `docker info` |
| `ImagePullBackOff` | Match the image tag, load it into `gratitude`, and check pull policy |
| Application pods Pending | Inspect events, resource requests, Docker capacity, and PVC binding |
| Health checker returns stale readiness | Inspect API connectivity, logs, and ServiceAccount RBAC |
| Prometheus target missing | Check ServiceMonitor namespace/label selectors and Service labels |
| Frontend loads but API calls fail | Configure shared routing; frontend-only forwarding serves assets |

See the [Sprint 1 troubleshooting section](docs/kind/SPRINT-1.md#16-troubleshooting)
for detailed diagnosis and expected results.

## Storage, resource use, and cleanup

The local cluster uses your machine's compute and disk. Bound Prometheus retention,
set resource requests/limits, stop temporary load tests, and inspect Docker disk
usage during longer experiments.

Local PVCs survive pod recreation but can constrain placement to their worker.
They do not provide replicated storage or survive deleting the KinD cluster.
Export evidence and any application data you want to keep before cleanup.

To retain the lab, stop port-forwards and keep the cluster. To remove the entire
disposable cluster and its local volumes, deliberately run:

```bash
kind delete cluster --name gratitude
```

Source files remain in the repository. Recreating the cluster requires reloading
images and reapplying resources in the guide's dependency order.

## Expected final deliverables

- Reproducible local KinD deployment of GratitudeApp and the monitoring stack.
- Health-checker API and metrics with scoped Kubernetes permissions.
- Controlled pod remediation with durable action history.
- Demonstrated HPA behavior, workload placement, and documented KinD capacity limits.
- Tested alert and recovery notifications through Slack.
- Grafana dashboards, implementation guides, troubleshooting, and demo evidence.

These are target outcomes across all six sprints, not a statement that every
feature is already implemented.

## Evaluation criteria

| Category | Weight |
|---|---|
| Documentation | 15% |
| Implementation | 75% |
| Cost optimization | 10% |
