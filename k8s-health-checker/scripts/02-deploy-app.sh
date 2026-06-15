#!/usr/bin/env bash
#
# scripts/02-deploy-app.sh
#
# Deploys RBAC, the health-checker app, and the kube-prometheus-stack
# (Prometheus + Grafana + Alertmanager) onto the already-provisioned
# EKS cluster.
#
# Prerequisites:
#   - scripts/01-provision-eks.sh has been run successfully
#   - kubectl is configured against the EKS cluster
#   - helm 3.x
#   - Docker image for the app has been built & pushed to ECR, and
#     deploy/k8s/deployment.yaml has been updated with the image URI
#     (see scripts/00-build-and-push.sh)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Applying RBAC and namespace..."
kubectl apply -f "$ROOT_DIR/deploy/k8s/rbac.yaml"

echo "==> Deploying health-checker app..."
kubectl apply -f "$ROOT_DIR/deploy/k8s/deployment.yaml"

echo "==> Adding prometheus-community Helm repo..."
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null 2>&1 || true
helm repo update

echo "==> Installing kube-prometheus-stack (Prometheus, Grafana, Alertmanager)..."
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  -f "$ROOT_DIR/deploy/prometheus/prometheus-values.yaml"

echo "==> Waiting for app pods to become ready..."
kubectl wait --for=condition=Ready pods -l app=health-checker -n health-checker --timeout=180s || true

echo "==> Waiting for monitoring pods to become ready..."
kubectl wait --for=condition=Ready pods --all -n monitoring --timeout=300s || true

echo "==> Status:"
kubectl get pods -n health-checker
kubectl get pods -n monitoring

echo ""
echo "To access the app locally:"
echo "  kubectl port-forward -n health-checker svc/health-checker 8000:80"
echo "  curl http://localhost:8000/api/nodes"
echo ""
echo "To access Grafana:"
echo "  kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80"
echo "  open http://localhost:3000 (admin / changeme)"
