#!/usr/bin/env bash
#
# scripts/setup-cluster-access.sh
#
# Sprint 1 helper script:
#   1. Creates a local kind cluster (skipped if one already exists)
#   2. Applies RBAC for the health-checker ServiceAccount
#   3. Installs the kube-prometheus-stack (Prometheus + Grafana + Alertmanager)
#
# Prerequisites: kind, kubectl, helm must be installed and on PATH.

set -euo pipefail

CLUSTER_NAME="health-checker-dev"

echo "==> Checking for existing kind cluster '${CLUSTER_NAME}'..."
if ! kind get clusters | grep -q "^${CLUSTER_NAME}$"; then
  echo "==> Creating kind cluster '${CLUSTER_NAME}'..."
  kind create cluster --name "${CLUSTER_NAME}"
else
  echo "==> Cluster '${CLUSTER_NAME}' already exists, skipping creation."
fi

echo "==> Verifying cluster access..."
kubectl cluster-info
kubectl get nodes

echo "==> Applying RBAC for health-checker ServiceAccount..."
kubectl apply -f "$(dirname "$0")/../deploy/k8s/rbac.yaml"

echo "==> Adding prometheus-community Helm repo..."
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null 2>&1 || true
helm repo update

echo "==> Installing kube-prometheus-stack (Prometheus, Grafana, Alertmanager)..."
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  -f "$(dirname "$0")/../deploy/prometheus/prometheus-values.yaml"

echo "==> Waiting for monitoring pods to become ready..."
kubectl wait --for=condition=Ready pods --all -n monitoring --timeout=300s || true

echo "==> Done. Monitoring namespace status:"
kubectl get pods -n monitoring

echo ""
echo "To access Grafana locally, run:"
echo "  kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80"
echo "Then open http://localhost:3000 (user: admin / pass: changeme)"
