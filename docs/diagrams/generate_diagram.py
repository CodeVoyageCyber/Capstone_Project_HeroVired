"""
Architecture diagram generator for GratitudeApp + K8s Health Checker capstone.
Run:  python3 docs/diagrams/generate_diagram.py
Output: docs/diagrams/architecture.png
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

fig, ax = plt.subplots(figsize=(22, 16))
ax.set_xlim(0, 22)
ax.set_ylim(0, 16)
ax.axis("off")
fig.patch.set_facecolor("#F0F4F8")

# ──────────────────────────────────────────────
# Colour palette
# ──────────────────────────────────────────────
C_AWS        = "#FF9900"
C_EKS_BG    = "#E8F4FD"
C_EKS_EDGE  = "#1A6FA8"
C_DEFAULT_NS = "#EBF5EB"
C_DEFAULT_EDGE = "#27AE60"
C_MON_NS    = "#FDF6EC"
C_MON_EDGE  = "#E67E22"
C_SVC       = "#2980B9"
C_GRPC      = "#8E44AD"
C_HC        = "#16A085"
C_PROM      = "#E74C3C"
C_GRAF      = "#F39C12"
C_ALERT     = "#C0392B"
C_EXT       = "#7F8C8D"
C_USER      = "#2C3E50"
C_DB        = "#795548"
C_FIS       = "#D32F2F"
C_SLACK     = "#4A154B"
C_ECR       = "#FF9900"
C_S3        = "#3F51B5"
C_DOCKER    = "#0DB7ED"

def box(ax, x, y, w, h, fc, ec, lw=1.5, radius=0.3, alpha=0.9, zorder=2):
    rect = FancyBboxPatch((x, y), w, h,
                          boxstyle=f"round,pad=0,rounding_size={radius}",
                          facecolor=fc, edgecolor=ec, linewidth=lw,
                          alpha=alpha, zorder=zorder)
    ax.add_patch(rect)

def label(ax, x, y, text, fs=8, color="white", bold=False, zorder=5, ha="center", va="center"):
    weight = "bold" if bold else "normal"
    ax.text(x, y, text, fontsize=fs, color=color, ha=ha, va=va,
            weight=weight, zorder=zorder, wrap=False)

def arrow(ax, x1, y1, x2, y2, color="#555555", lw=1.2, style="->", zorder=4):
    ax.annotate("",
                xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle=style, color=color,
                                lw=lw, connectionstyle="arc3,rad=0.0"),
                zorder=zorder)

def svc_box(ax, x, y, w, h, label_text, port, fc, label_fs=7.2):
    box(ax, x, y, w, h, fc=fc, ec="white", lw=1.2, radius=0.2, zorder=5)
    ax.text(x + w/2, y + h/2 + 0.06, label_text, fontsize=label_fs,
            color="white", ha="center", va="center", weight="bold", zorder=6)
    if port:
        ax.text(x + w/2, y + h/2 - 0.22, f":{port}", fontsize=6,
                color="white", ha="center", va="center", zorder=6, alpha=0.85)

# ══════════════════════════════════════════════
# 0. TITLE
# ══════════════════════════════════════════════
ax.text(11, 15.55, "GratitudeApp — K8s Cluster Health Checker  |  Architecture",
        fontsize=15, color=C_USER, ha="center", va="center", weight="bold", zorder=10)
ax.text(11, 15.1, "Amazon EKS  ·  Python / FastAPI  ·  Prometheus / Grafana  ·  AWS FIS Chaos Testing",
        fontsize=9, color="#555", ha="center", va="center", zorder=10)

# ══════════════════════════════════════════════
# 1. AWS BOUNDARY
# ══════════════════════════════════════════════
box(ax, 0.3, 0.4, 21.2, 14.4, fc="#FFFDE7", ec=C_AWS, lw=2.5, radius=0.5, alpha=0.6, zorder=1)
label(ax, 1.5, 14.6, "Amazon Web Services (us-east-1)", fs=9, color=C_AWS, bold=True, zorder=3, ha="left")

# ══════════════════════════════════════════════
# 2. EKS CLUSTER BOUNDARY
# ══════════════════════════════════════════════
box(ax, 0.7, 0.7, 16.2, 13.2, fc=C_EKS_BG, ec=C_EKS_EDGE, lw=2, radius=0.4, alpha=0.6, zorder=1)
label(ax, 2.2, 13.7, "Amazon EKS — gratitude-health-cluster  (2× t3.medium, EBS CSI, OIDC, ingress-nginx NLB)",
      fs=8, color=C_EKS_EDGE, bold=True, zorder=3, ha="left")

# ══════════════════════════════════════════════
# 3. DEFAULT NAMESPACE  (GratitudeApp + health-checker)
# ══════════════════════════════════════════════
box(ax, 0.9, 0.9, 10.8, 12.3, fc=C_DEFAULT_NS, ec=C_DEFAULT_EDGE, lw=1.5, radius=0.3, alpha=0.5, zorder=1)
label(ax, 1.5, 13.0, "namespace: default", fs=8, color=C_DEFAULT_EDGE, bold=True, zorder=3, ha="left")

# ── GratitudeApp services label ──
ax.text(1.2, 12.6, "GratitudeApp  (9 microservices)", fontsize=8, color="#1A5276",
        ha="left", va="center", style="italic", zorder=4)

# ── Client ──
svc_box(ax, 1.05, 11.6, 2.0, 0.7, "Client\n(React/Nginx)", "3000", "#1565C0")

# ── API Gateway ──
svc_box(ax, 1.05, 10.4, 2.0, 0.7, "API Gateway", "5000", C_SVC)

# ── Server Main ──
svc_box(ax, 1.05, 9.2, 2.0, 0.7, "Server Main\n(auth/core)", "5001", C_SVC)

# ── Entries ──
svc_box(ax, 3.5, 11.6, 2.0, 0.7, "Entries\nService", "50051", C_GRPC)

# ── Moods API + gRPC ──
svc_box(ax, 3.5, 10.4, 2.0, 0.7, "Moods API", "5002", C_SVC)
svc_box(ax, 3.5, 9.2,  2.0, 0.7, "Moods\nService", "50052", C_GRPC)

# ── Stats API + gRPC ──
svc_box(ax, 6.0, 10.4, 2.0, 0.7, "Stats API", "5003", C_SVC)
svc_box(ax, 6.0, 9.2,  2.0, 0.7, "Stats\nService", "50053", C_GRPC)

# ── Files Service ──
svc_box(ax, 6.0, 11.6, 2.0, 0.7, "Files\nService", "5004", "#00695C")

# ── Postgres ──
svc_box(ax, 4.0, 7.8, 2.5, 0.8, "PostgreSQL", "5432", C_DB)

# Arrows: client → api-gateway
arrow(ax, 2.05, 11.6, 2.05, 11.1, color="#1565C0", lw=1.2)
# api-gateway → server
arrow(ax, 2.05, 10.4, 2.05, 9.9, color=C_SVC, lw=1.2)
# api-gateway → entries
arrow(ax, 3.05, 10.75, 3.5, 11.95, color=C_GRPC, lw=1.0)
# api-gateway → moods-api
arrow(ax, 3.05, 10.75, 3.5, 10.75, color=C_SVC, lw=1.0)
# api-gateway → stats-api
arrow(ax, 3.05, 10.75, 6.0, 10.75, color=C_SVC, lw=1.0)
# api-gateway → files
arrow(ax, 3.05, 10.75, 6.0, 11.95, color="#00695C", lw=1.0)
# moods-api → moods-service (gRPC)
arrow(ax, 4.5, 10.4, 4.5, 9.9, color=C_GRPC, lw=1.0)
# stats-api → stats-service (gRPC)
arrow(ax, 7.0, 10.4, 7.0, 9.9, color=C_GRPC, lw=1.0)
# services → postgres
arrow(ax, 4.5, 9.2, 5.0, 8.6, color=C_DB, lw=1.0)
arrow(ax, 7.0, 9.2, 5.4, 8.6, color=C_DB, lw=1.0)
arrow(ax, 2.05, 9.2, 4.0, 8.35, color=C_DB, lw=1.0)

# ── Health Checker box inside default ns ──
box(ax, 1.0, 1.1, 9.6, 5.8, fc="#E8F8F5", ec=C_HC, lw=1.5, radius=0.3, alpha=0.7, zorder=2)
label(ax, 1.5, 6.7, "Health Checker (FastAPI / Python)", fs=8, color=C_HC, bold=True, zorder=5, ha="left")

# HC sub-components
svc_box(ax, 1.2, 5.4, 2.8, 0.8, "FastAPI App\n/healthz  /metrics", "", C_HC, label_fs=7.5)
svc_box(ax, 4.4, 5.4, 2.8, 0.8, "REST API\n/api/nodes /api/pods", "", C_HC, label_fs=7.5)
svc_box(ax, 7.2, 5.4, 2.2, 0.8, "REST API\n/api/deployments", "", C_HC, label_fs=7.5)

svc_box(ax, 1.2, 3.9, 2.8, 0.9, "monitor.py\npoll every 15 s", "", "#0E7C67", label_fs=7.5)
svc_box(ax, 4.4, 3.9, 2.8, 0.9, "k8s_client.py\nK8s Python Client", "", "#0E7C67", label_fs=7.5)
svc_box(ax, 7.2, 3.9, 2.2, 0.9, "Prometheus\nGauges", "", "#C0392B", label_fs=7.5)

svc_box(ax, 1.2, 1.3, 8.2, 0.9, "RBAC: ClusterRole → read nodes/pods/services/events  |  update deployments/replicasets/HPAs",
        "", "#5D6D7E", label_fs=7.0)

# HC internal arrows
arrow(ax, 2.6, 5.4, 2.6, 4.8, color=C_HC, lw=1)
arrow(ax, 5.8, 5.4, 5.8, 4.8, color=C_HC, lw=1)
arrow(ax, 8.3, 5.4, 8.3, 4.8, color="#C0392B", lw=1)
arrow(ax, 5.8, 3.9, 5.8, 3.5, color="#0E7C67", lw=0.8)

# HC polls K8s API (upward arrow from k8s_client to services)
ax.annotate("", xy=(5.8, 9.2), xytext=(5.8, 4.8),
            arrowprops=dict(arrowstyle="<->", color="#0E7C67", lw=1.3,
                            connectionstyle="arc3,rad=0.0"), zorder=4)
ax.text(6.05, 7.0, "K8s API\n(polling)", fontsize=6.5, color="#0E7C67", ha="left", va="center", zorder=5)

# ══════════════════════════════════════════════
# 4. MONITORING NAMESPACE
# ══════════════════════════════════════════════
box(ax, 11.9, 0.9, 4.8, 12.3, fc=C_MON_NS, ec=C_MON_EDGE, lw=1.5, radius=0.3, alpha=0.55, zorder=1)
label(ax, 12.1, 13.0, "namespace: monitoring", fs=8, color=C_MON_EDGE, bold=True, zorder=3, ha="left")

# kube-prometheus-stack label
ax.text(12.1, 12.6, "kube-prometheus-stack (Helm)", fontsize=7.5,
        color="#784212", ha="left", va="center", style="italic", zorder=4)

# Prometheus
svc_box(ax, 12.1, 10.8, 4.3, 1.1, "Prometheus\n15d retention · gp3 PVC", "", C_PROM, label_fs=8.5)

# Grafana
svc_box(ax, 12.1, 9.1, 4.3, 1.1, "Grafana\nLive dashboards · port 3000", "", C_GRAF, label_fs=8.5)

# Alertmanager
svc_box(ax, 12.1, 7.4, 4.3, 1.1, "Alertmanager\nRouting · severity levels", "", C_ALERT, label_fs=8.5)

# PrometheusRule box
svc_box(ax, 12.1, 5.7, 4.3, 1.1, "PrometheusRules\nnode NotReady, pod restarts, replica mismatch", "", "#6D4C41", label_fs=7.2)

# Monitoring arrows
arrow(ax, 14.25, 9.1, 14.25, 11.9, color=C_PROM, lw=1.2)  # prom → grafana (up)
arrow(ax, 14.25, 7.4, 14.25, 9.1, color=C_ALERT, lw=1.2)  # alertmanager ← prometheus
arrow(ax, 14.25, 5.7, 14.25, 7.4, color="#6D4C41", lw=1.2)  # rules → alertmanager

# Prometheus scrapes health-checker /metrics
ax.annotate("",
            xy=(11.9, 6.0), xytext=(10.6, 6.0),
            arrowprops=dict(arrowstyle="<-", color=C_PROM, lw=1.3,
                            connectionstyle="arc3,rad=0.0"), zorder=4)
ax.text(11.0, 6.25, "scrape\n/metrics", fontsize=6.5, color=C_PROM, ha="center", va="center", zorder=5)

# ══════════════════════════════════════════════
# 5. EXTERNAL SERVICES (right column)
# ══════════════════════════════════════════════
# ingress-nginx / NLB
box(ax, 17.1, 11.6, 3.9, 1.6, fc="#EAF2FF", ec="#1A6FA8", lw=1.5, radius=0.3, zorder=3)
label(ax, 19.05, 12.55, "ingress-nginx\n(AWS NLB)", fs=8.5, color="#1A6FA8", bold=True, zorder=5)
label(ax, 19.05, 12.05, "ingressClassName: nginx", fs=7, color="#555", zorder=5)

# AWS FIS
box(ax, 17.1, 9.6, 3.9, 1.6, fc="#FFEBEE", ec=C_FIS, lw=1.5, radius=0.3, zorder=3)
label(ax, 19.05, 10.55, "AWS FIS", fs=8.5, color=C_FIS, bold=True, zorder=5)
label(ax, 19.05, 10.05, "Chaos / Fault Injection", fs=7, color="#555", zorder=5)

# Slack
box(ax, 17.1, 7.6, 3.9, 1.6, fc="#F3E5F5", ec=C_SLACK, lw=1.5, radius=0.3, zorder=3)
label(ax, 19.05, 8.55, "Slack", fs=8.5, color=C_SLACK, bold=True, zorder=5)
label(ax, 19.05, 8.05, "Real-time alerts (webhook)", fs=7, color="#555", zorder=5)

# ECR
box(ax, 17.1, 5.6, 3.9, 1.6, fc="#FFF8E1", ec=C_ECR, lw=1.5, radius=0.3, zorder=3)
label(ax, 19.05, 6.55, "Amazon ECR", fs=8.5, color=C_ECR, bold=True, zorder=5)
label(ax, 19.05, 6.05, "Health-checker image", fs=7, color="#555", zorder=5)

# Amazon S3
box(ax, 17.1, 3.6, 3.9, 1.6, fc="#E8EAF6", ec=C_S3, lw=1.5, radius=0.3, zorder=3)
label(ax, 19.05, 4.55, "Amazon S3", fs=8.5, color=C_S3, bold=True, zorder=5)
label(ax, 19.05, 4.05, "File uploads (files-service)", fs=7, color="#555", zorder=5)

# Docker Hub
box(ax, 17.1, 1.6, 3.9, 1.6, fc="#E3F2FD", ec=C_DOCKER, lw=1.5, radius=0.3, zorder=3)
label(ax, 19.05, 2.55, "Docker Hub", fs=8.5, color=C_DOCKER, bold=True, zorder=5)
label(ax, 19.05, 2.05, "prashantdey/merndemoapp:*", fs=7, color="#555", zorder=5)

# ══════════════════════════════════════════════
# 6. END USER
# ══════════════════════════════════════════════
box(ax, 0.5, 14.0, 2.5, 0.9, fc="#2C3E50", ec="#2C3E50", lw=1.5, radius=0.3, zorder=3)
label(ax, 1.75, 14.45, "End Users", fs=9, color="white", bold=True, zorder=5)

# Developer / DevOps
box(ax, 3.5, 14.0, 3.0, 0.9, fc="#34495E", ec="#34495E", lw=1.5, radius=0.3, zorder=3)
label(ax, 5.0, 14.45, "DevOps / Developer", fs=8.5, color="white", bold=True, zorder=5)

# ══════════════════════════════════════════════
# 7. CONNECTION ARROWS (cross-boundary)
# ══════════════════════════════════════════════
# Users → ingress-nginx
arrow(ax, 1.75, 14.0, 18.0, 13.2, color="#1A6FA8", lw=1.5)
ax.text(10.5, 14.1, "HTTPS", fontsize=7, color="#1A6FA8", ha="center", zorder=5)

# ingress-nginx → client
arrow(ax, 17.1, 12.4, 3.05, 11.95, color="#1A6FA8", lw=1.3)

# Alertmanager → Slack
arrow(ax, 17.1, 8.4, 16.95, 8.4, color=C_SLACK, lw=1.3)

# Health-checker → ECR (pull image)
arrow(ax, 9.6, 3.5, 17.1, 6.4, color=C_ECR, lw=1.0, style="<-")

# files-service → S3
arrow(ax, 8.0, 11.95, 17.1, 4.4, color=C_S3, lw=1.0)

# Docker Hub → cluster (image pull)
arrow(ax, 9.6, 1.8, 17.1, 2.4, color=C_DOCKER, lw=1.0, style="<-")

# FIS → pods (chaos)
ax.annotate("", xy=(8.5, 9.55), xytext=(17.1, 10.4),
            arrowprops=dict(arrowstyle="->", color=C_FIS, lw=1.3,
                            connectionstyle="arc3,rad=-0.25"), zorder=4)
ax.text(14.2, 10.95, "chaos inject", fontsize=6.5, color=C_FIS, ha="center", zorder=5)

# DevOps → k8s cluster (kubectl/eksctl)
ax.annotate("", xy=(0.9, 7.5), xytext=(3.5, 14.0),
            arrowprops=dict(arrowstyle="->", color="#34495E", lw=1.2,
                            connectionstyle="arc3,rad=0.3"), zorder=4)
ax.text(0.45, 11.0, "kubectl\nexsctl", fontsize=6.5, color="#34495E",
        ha="center", va="center", zorder=5)

# Grafana port-forward (devops)
ax.annotate("", xy=(12.1, 9.65), xytext=(5.0, 14.0),
            arrowprops=dict(arrowstyle="<->", color="#F39C12", lw=1.1,
                            connectionstyle="arc3,rad=-0.2"), zorder=4)
ax.text(9.5, 13.35, "port-forward\nGrafana :3000", fontsize=6.5, color="#F39C12",
        ha="center", va="center", zorder=5)

# ══════════════════════════════════════════════
# 8. LEGEND
# ══════════════════════════════════════════════
legend_items = [
    (C_SVC,  "REST API service"),
    (C_GRPC, "gRPC service"),
    (C_HC,   "Health Checker (FastAPI)"),
    (C_DB,   "PostgreSQL DB"),
    (C_PROM, "Prometheus"),
    (C_GRAF, "Grafana"),
    (C_ALERT,"Alertmanager"),
    (C_FIS,  "AWS FIS (chaos)"),
]
lx, ly = 11.9, 4.9
ax.text(lx, ly + 0.4, "Legend", fontsize=8, color="#333", weight="bold",
        ha="left", va="center", zorder=5)
for i, (color, txt) in enumerate(legend_items):
    row = i // 2
    col = i % 2
    bx = lx + col * 2.5
    by = ly - row * 0.45
    box(ax, bx, by - 0.15, 0.35, 0.3, fc=color, ec="white", lw=0.8, radius=0.05, zorder=5)
    ax.text(bx + 0.45, by, txt, fontsize=6.5, color="#333",
            ha="left", va="center", zorder=5)

# ══════════════════════════════════════════════
# 9. PROTO badge
# ══════════════════════════════════════════════
ax.text(5.5, 12.6, "gRPC protos: entries · moods · stats", fontsize=6.5,
        color=C_GRPC, ha="center", va="center", style="italic", zorder=5)

plt.tight_layout(pad=0)
out_path = "docs/diagrams/architecture.png"
plt.savefig(out_path, dpi=180, bbox_inches="tight", facecolor=fig.get_facecolor())
print(f"Saved: {out_path}")
