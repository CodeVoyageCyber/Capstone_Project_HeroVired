#!/usr/bin/env bash
# =============================================================================
# scripts/99-teardown.sh
#
# Full teardown script for GratitudeApp Health-Checker capstone project.
# Removes all Kubernetes resources, Helm releases, and optionally the Minikube
# cluster itself.
#
# Usage:
#   chmod +x scripts/99-teardown.sh
#   ./scripts/99-teardown.sh [--delete-cluster]
#
# Options:
#   --delete-cluster   Fully delete the Minikube cluster (minikube delete)
#                      Default: only stops the cluster (minikube stop)
# =============================================================================

set -euo pipefail

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'  # No Color

log()  { echo -e "${CYAN}[INFO]${NC} $*"; }
ok()   { echo -e "${GREEN}[OK]${NC}   $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[ERR]${NC}  $*"; }

DELETE_CLUSTER=false
for arg in "$@"; do
  case "$arg" in
    --delete-cluster) DELETE_CLUSTER=true ;;
    --help|-h)
      echo "Usage: $0 [--delete-cluster]"
      echo "  --delete-cluster  Permanently delete Minikube cluster (minikube delete)"
      exit 0
      ;;
    *) warn "Unknown argument: $arg" ;;
  esac
done

echo ""
echo -e "${BOLD}╔═══════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   GratitudeApp Health-Checker — Teardown      ║${NC}"
echo -e "${BOLD}╚═══════════════════════════════════════════════╝${NC}"
echo ""

# ── Step 1: Remove load generator (if deployed) ───────────────────────────────
log "Step 1/7 — Removing load generator (if deployed)..."
if kubectl get deployment load-generator -n default &>/dev/null 2>&1; then
  kubectl delete deployment load-generator -n default --ignore-not-found=true
  ok "Load generator removed."
else
  ok "Load generator not found — skipping."
fi

# ── Step 2: Remove chaos / FIS RBAC ──────────────────────────────────────────
log "Step 2/7 — Removing chaos/FIS RBAC resources..."
if [ -d "k8s-health-checker/chaos" ]; then
  kubectl delete -f k8s-health-checker/chaos/ --ignore-not-found=true 2>/dev/null || true
  ok "Chaos/FIS RBAC resources removed."
else
  warn "k8s-health-checker/chaos/ not found — skipping."
fi

# ── Step 3: Remove HPAs ───────────────────────────────────────────────────────
log "Step 3/7 — Removing Horizontal Pod Autoscalers..."
kubectl delete -f k8s-health-checker/deploy/autoscaling/ --ignore-not-found=true 2>/dev/null || true
ok "HPAs removed."

# ── Step 4: Remove health-checker deployment ──────────────────────────────────
log "Step 4/7 — Removing health-checker app and all deploy manifests..."

# Grafana dashboards
kubectl delete -f k8s-health-checker/deploy/grafana/ \
  --ignore-not-found=true 2>/dev/null || true

# Alert rules and Alertmanager config
kubectl delete -f k8s-health-checker/deploy/alerts/ \
  --ignore-not-found=true 2>/dev/null || true

# Health-checker deployment, service, ServiceMonitor, RBAC
kubectl delete -f k8s-health-checker/deploy/healthchecker/ \
  --ignore-not-found=true 2>/dev/null || true

ok "Health-checker resources removed."

# ── Step 5: Remove GratitudeApp ───────────────────────────────────────────────
log "Step 5/7 — Removing GratitudeApp microservices..."
if [ -d "k8s-local" ]; then
  kubectl delete -f k8s-local/ --ignore-not-found=true 2>/dev/null || true
  ok "GratitudeApp removed."

  # Wait for pods to terminate
  log "  Waiting for default namespace pods to terminate (up to 60s)..."
  timeout 60 bash -c '
    while kubectl get pods -n default --field-selector=status.phase!=Failed 2>/dev/null \
          | grep -qv "^NAME\|No resources"; do
      echo "  Waiting for pods to terminate..."
      sleep 5
    done
  ' || warn "Some pods may still be terminating — check with: kubectl get pods -n default"
else
  warn "k8s-local/ not found — skipping GratitudeApp teardown."
fi

# ── Step 6: Uninstall Helm monitoring stack ───────────────────────────────────
log "Step 6/7 — Uninstalling kube-prometheus-stack Helm release..."
if helm list -n monitoring 2>/dev/null | grep -q "monitoring"; then
  helm uninstall monitoring -n monitoring
  ok "Helm release 'monitoring' uninstalled."
else
  warn "Helm release 'monitoring' not found — may already be removed."
fi

log "  Deleting monitoring namespace..."
kubectl delete namespace monitoring --ignore-not-found=true 2>/dev/null || true

# Wait for namespace to be fully deleted
log "  Waiting for monitoring namespace to terminate (up to 90s)..."
timeout 90 bash -c '
  while kubectl get namespace monitoring &>/dev/null 2>&1; do
    echo "  Waiting for monitoring namespace deletion..."
    sleep 5
  done
' || warn "Namespace 'monitoring' may still be terminating — check with: kubectl get ns monitoring"

ok "Monitoring namespace removed."

# ── Step 7: Minikube teardown ─────────────────────────────────────────────────
log "Step 7/7 — Minikube teardown..."
if $DELETE_CLUSTER; then
  warn "Deleting entire Minikube cluster (--delete-cluster flag set)..."
  minikube delete
  ok "Minikube cluster deleted."
else
  log "Stopping Minikube (cluster data preserved)..."
  minikube stop
  ok "Minikube stopped. Cluster data preserved."
  echo ""
  echo -e "  ${YELLOW}Tip:${NC} To permanently delete the cluster, run:"
  echo -e "  ${BOLD}  minikube delete${NC}"
  echo -e "  or re-run this script with:"
  echo -e "  ${BOLD}  ./scripts/99-teardown.sh --delete-cluster${NC}"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}╔═══════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║             ✅ Teardown Complete!              ║${NC}"
echo -e "${BOLD}╚═══════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${GREEN}All GratitudeApp and Health-Checker resources have been removed.${NC}"
echo ""
echo -e "  To redeploy from scratch:"
echo -e "  ${BOLD}  minikube start --cpus=4 --memory=8192 --driver=docker --addons=metrics-server,ingress${NC}"
echo -e "  ${BOLD}  kubectl apply -f k8s-local/${NC}"
echo -e "  ${BOLD}  # See Readme_Local_Sprint6.md for the full setup walkthrough${NC}"
echo ""
