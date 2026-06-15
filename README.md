# Kubernetes Cluster Health Checker and Auto-Healing

An automated health monitoring and self-healing tool for Kubernetes
clusters. It watches node and pod health, automatically recovers from
common failure modes (failed pods, unresponsive nodes, resource
imbalance), sends real-time alerts to Slack/Teams, and exposes a web
dashboard for live and historical visibility.

## Problem Statement

Manually monitoring and remediating Kubernetes clusters is time-consuming
and error-prone, especially for small DevOps teams running large
clusters. This project automates detection and recovery of common
issues (failed pods, unresponsive nodes, resource pressure) to reduce
downtime and manual toil, while keeping the team informed via alerts
and a dashboard.

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
| Go | Core service — performance, native Kubernetes API client |
| Python | Scripting and initial data processing utilities |
| Kubernetes API (client-go) | Interact with and manage cluster resources |
| Prometheus | Metrics collection from the cluster |
| Grafana | Visualization / dashboard |
| Alertmanager | Routes alerts to Slack/Teams |
| Slack API | Notifications to the DevOps team |
| Docker | Containerize the application for deployment |

## Project Structure

```
k8s-health-checker/
├── cmd/
│   └── healthchecker/      # main application entrypoint
├── internal/
│   ├── k8sclient/           # Kubernetes API client wrapper
│   ├── monitor/             # health monitoring logic (Sprint 2)
│   ├── healer/               # self-healing logic (Sprint 3-4)
│   ├── alerting/             # alerting/notification logic (Sprint 5)
│   └── config/               # configuration loading
├── deploy/
│   ├── docker/               # Dockerfile(s)
│   ├── k8s/                  # Kubernetes manifests (RBAC, deployment)
│   └── prometheus/           # Prometheus/Grafana Helm values
├── scripts/                   # setup and helper scripts
├── docs/                       # additional documentation
├── go.mod / go.sum
└── README.md
```

## Prerequisites

- Go 1.22+
- Docker
- `kubectl`
- `kind` (or `minikube`) for a local development cluster
- `helm` 3.x

---

## Sprint-by-Sprint Progress

### Sprint 1: Project Setup and Kubernetes Cluster Access ✅

**Goal:** Establish a foundation for the project by setting up the
necessary environment, tools, and access to Kubernetes resources.

**What was done:**

1. **Project structure and repository initialized.**
   Created the Go module (`go.mod`), standard `cmd/` + `internal/`
   layout, `.gitignore`, and directories for deployment manifests,
   scripts, and documentation. The structure separates the
   application entrypoint (`cmd/healthchecker`) from reusable
   internal packages (`internal/k8sclient`, `internal/monitor`,
   `internal/healer`, `internal/alerting`, `internal/config`) so
   future sprints can add functionality without restructuring.

2. **Kubernetes cluster access configured.**
   A local development cluster is created with `kind`
   (`scripts/setup-cluster-access.sh`), giving a free, disposable
   cluster for development and testing — avoiding cloud costs during
   development (relevant to the Cost Optimization criterion). The
   same code works against any standard kubeconfig-based cluster
   (EKS/GKE/AKS) for production.

3. **Basic API access to Kubernetes resources.**
   `internal/k8sclient/client.go` provides a `NewClient()` function
   that returns a `client-go` Clientset. It automatically uses
   in-cluster configuration when running as a pod (via its
   ServiceAccount) and falls back to the local `~/.kube/config` (or
   `$KUBECONFIG`) for development.
   `deploy/k8s/rbac.yaml` defines a `health-checker` ServiceAccount,
   ClusterRole, and ClusterRoleBinding with the minimum permissions
   needed for later sprints: read/list/watch/delete on pods, nodes,
   services, events; update on deployments/replicasets; and
   create/update on HorizontalPodAutoscalers.
   `cmd/healthchecker/main.go` is a smoke-test entrypoint that
   connects to the cluster and lists all nodes and pods, confirming
   API access works end-to-end.

4. **Prometheus installed and configured for Kubernetes.**
   The `kube-prometheus-stack` Helm chart (Prometheus + Grafana +
   Alertmanager bundled together) is installed via
   `scripts/setup-cluster-access.sh` using
   `deploy/prometheus/prometheus-values.yaml`, which sets
   conservative resource requests/limits and a 7-day retention period
   suitable for a small dev cluster. This single chart also lays the
   groundwork for Sprint 2 (metrics), Sprint 5 (Alertmanager), and
   Sprint 6 (Grafana dashboard).

**How to run Sprint 1:**

```bash
# 1. Set up cluster, RBAC, and Prometheus stack
./scripts/setup-cluster-access.sh

# 2. Run the smoke test to confirm API access
go mod tidy
go run ./cmd/healthchecker

# 3. Access Grafana (bundled with Prometheus stack)
kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80
# open http://localhost:3000 (admin / changeme)
```

**Deliverable:** A working repository skeleton, a local Kubernetes
cluster the application can authenticate against, a Go client capable
of listing cluster resources, and a running Prometheus/Grafana/
Alertmanager stack in the `monitoring` namespace.

---

### Sprint 2: Health Monitoring Module (Node & Pod Checks) ⬜ Planned

**Goal:** Enable basic health checks on nodes and pods and set up
alerts for critical issues.

**Planned work:**
- Build `internal/monitor` to watch node conditions (Ready,
  MemoryPressure, DiskPressure, etc.) and pod statuses (Running,
  Pending, CrashLoopBackOff, etc.) via the Kubernetes API.
- Expose custom Prometheus metrics (e.g.
  `healthchecker_node_ready`, `healthchecker_pod_restarts_total`) via
  a `/metrics` endpoint and configure a `ServiceMonitor` so Prometheus
  scrapes them.
- Add Grafana dashboards visualizing node/pod health and resource
  usage (CPU, memory).
- Define initial Alertmanager rules for thresholds (e.g. node
  NotReady > 2 minutes, pod restart count > N).

---

### Sprint 3: Self-Healing Mechanisms (Pod Recovery) ⬜ Planned

**Goal:** Automate pod recovery processes and ensure that self-healing
actions are logged for transparency.

**Planned work:**
- Build `internal/healer` to detect and restart/reschedule
  unresponsive or failed pods.
- Add automated cleanup for pods stuck in `CrashLoopBackOff` or
  `Evicted` states.
- Validate self-healing behavior in a staging namespace/cluster.
- Implement structured audit logging of every healing action taken
  (what, when, why, result).

---

### Sprint 4: Advanced Self-Healing (Node Scaling & Resource Balancing) ⬜ Planned

**Goal:** Ensure the system can scale and balance resources
automatically, optimizing cluster performance and cost.

**Planned work:**
- Implement node scaling logic (cluster autoscaler integration or
  custom scale-up/down based on utilization).
- Configure Horizontal Pod Autoscalers for high-demand workloads.
- Add resource-balancing logic to redistribute pods across nodes.
- Load-test these behaviors under simulated traffic.

---

### Sprint 5: Alerting and Notification System Integration ⬜ Planned

**Goal:** Implement a comprehensive alerting and notification system to
keep the team informed of critical events and actions.

**Planned work:**
- Build `internal/alerting` to integrate with the Slack API (and
  optionally Microsoft Teams) for real-time notifications.
- Configure Alertmanager routing/receivers for multiple severity
  levels (info/warning/critical).
- End-to-end test alert delivery for both monitoring alerts and
  self-healing action notifications.
- Document alert setup and customization in `docs/`.

---

### Sprint 6: Web Dashboard and Project Documentation ⬜ Planned

**Goal:** Deliver a user-friendly dashboard for monitoring cluster
health and document the project for deployment in real-world
environments.

**Planned work:**
- Build out Grafana dashboards (or a lightweight custom web UI) showing
  live health status, historical trends, and auto-healing logs.
- Wire Prometheus metrics and alert/action history into the dashboard.
- Write full user documentation: setup, configuration, usage, and
  troubleshooting guides.
- Final end-to-end testing and feedback incorporation.

---

## Deliverables Summary

- Automated Health Monitoring Tool for Kubernetes clusters
- Self-Healing Mechanisms for both pod and node recovery
- Real-Time Alerting and Notifications through Slack/Teams
- Web Dashboard for real-time and historical monitoring
- Comprehensive Documentation for setup, usage, and troubleshooting

## Evaluation Criteria

| Category | Weight |
|---|---|
| Documentation | 15% |
| Implementation | 75% |
| Cost Optimization | 10% |
