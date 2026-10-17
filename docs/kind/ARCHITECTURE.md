# KinD project architecture, by sprint

![KinD architecture with sprint assignments](../diagrams/kind-architecture.png)

[Editable vector diagram](../diagrams/kind-architecture.svg)

This is the **target architecture**, inspired by the supplied diagram's nested boundaries, grouped services, and directed flows. It replaces the cloud-region boundary with a local Docker Desktop / KinD boundary. Sprint badges describe ownership of capabilities, not proof of completion. The Sprint 1 guide exists; live deployment has not been verified. Sprints 2–6 remain planned.

## Sprint mapping

| Sprint | Components and behavior |
|---|---|
| **S1 — Foundation** | Three-node KinD cluster; local Docker builds and image loading; namespaces; GratitudeApp and PostgreSQL PVC; Python API with read-only RBAC; ServiceMonitor; Prometheus, exporters, Grafana and Alertmanager installation. |
| **S2 — Health monitoring** | Detailed pod/node health and resource checks; initial Grafana panels; custom threshold-based Prometheus alert rules. |
| **S3 — Pod recovery** | Opt-in healing through Kubernetes API; scoped write RBAC; ownership validation, grace periods and cooldowns; durable audit history; controlled failure exercises. Kubernetes's built-in Deployment recovery already exists in S1. |
| **S4 — Scaling and balancing** | Metrics Server supplies HPA metrics; HPA changes workload replicas; topology spread improves placement; controlled load tests and worker-capacity simulation. KinD workers remain a fixed set of Docker containers. |
| **S5 — Notifications** | Alertmanager severity routing, Slack webhook Secret, healing notifications and delivery tests. Installation of Alertmanager in S1 does not configure Slack. |
| **S6 — Dashboard and handover** | Final Grafana health/resource/healing views, history and audit presentation, runbooks and end-to-end validation. The current S1 guide also defers shared browser API routing and local S3-compatible file storage to final application integration. |

Solid cards represent the documented Sprint 1 baseline. Dashed cards or flows identify future additions. Cards with multiple badges are installed early and enhanced later; their text identifies the split. The dashed **blue cluster boundary** denotes containment, not implementation status.

## Read the flows

1. The developer builds images locally, loads them into KinD, and applies resources using kubectl and Helm. Host Docker images must be loaded into the KinD node runtimes.
2. The health checker authenticates with its ServiceAccount and reads the Kubernetes API. Its observer is separate from Kubernetes's built-in reconciliation controllers.
3. Prometheus initiates scrapes of the health checker's `/metrics` using ServiceMonitor discovery. It also scrapes cluster exporters and kubelet/cAdvisor. The diagram's arrows identify the initiator/target of pulls, rather than the direction in which metric response bytes travel.
4. Grafana queries Prometheus for historical data. Sprint 3 should expose healing counters for dashboards; counters do not replace the durable per-action audit store. Displaying individual audit records requires an explicit read API or compatible Grafana data source in Sprint 6.
5. The Sprint 3 healer requests deletion of eligible unhealthy owned pods through the Kubernetes API; Deployment/ReplicaSet controllers create replacements. It does not restart arbitrary containers directly or recreate failed physical machines.
6. Prometheus evaluates alert rules and sends alerts to Alertmanager. Sprint 5 configures Alertmanager to deliver Slack notifications. Healing events need their own explicit integration, such as event-derived metrics/rules or a notifier; an audit record alone does not send a notification.
7. Metrics Server supplies the resource metrics API used by HPA. HPA and the scheduler are Kubernetes platform components, not part of the Python healing loop. Prometheus and Metrics Server serve different consumers.

## Local boundaries and limitations

- One control-plane and two workers share the laptop's CPU, RAM and Docker VM. They are not three independent machines.
- PostgreSQL, Prometheus and Grafana use local PVCs; a persistent audit PVC is planned for S3. These survive pod recreation but not cluster deletion, and local volumes can constrain rescheduling between workers.
- The S1 browser forward serves frontend assets only. The dashed frontend-to-backend flow requires future `/api` routing; direct API gateway forwarding is used for S1 journal validation.
- Local S3-compatible storage is planned, not configured in S1. OpenAI integration remains optional and external; core journaling does not require it.
- Slack is outside the local Docker/KinD boundary. Its webhook URL must be stored as a Secret and omitted from source control and screenshots.
- AWS EKS, ECR, NLB, FIS, IRSA and EBS are not required. No cloud-region replication or high availability is implied by this local diagram.

## Diagram source

The SVG is editable in a vector editor. Regenerate both exports from the repository root:

```bash
python3 docs/diagrams/generate-kind-architecture.py
python3 docs/diagrams/render-kind-architecture.py
```

The first script uses Python's standard library. The PNG renderer additionally requires ImageMagick (`magick`) and an installed font (Helvetica on macOS, DejaVu Sans otherwise).

Continue with the [Sprint 1 implementation guide](SPRINT-1.md).
