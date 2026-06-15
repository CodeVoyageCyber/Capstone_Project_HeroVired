#!/usr/bin/env bash
#
# scripts/03-deploy-monitoring.sh
#
# Deploys the health-checker app (RBAC + Deployment + Service) and the
# kube-prometheus-stack (Prometheus + Grafana + Alertmanager) onto the
# EKS cluster, alongside the already-deployed GratitudeApp.
#
# Prerequisites:
#   - scripts/01-provision-eks.sh and scripts/02-deploy-gratitudeapp.sh
#     have been run
#   - kubectl is configured against the EKS cluster
#   - helm 3.x
#   - The health-checker image has been built & pushed
#     (scripts/00-build-and-push-healthchecker.sh), and
#     deploy/healthchecker/deployment.yaml's image field updated

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Applying health-checker RBAC..."
kubectl apply -f "$ROOT_DIR/deploy/healthchecker/rbac.yaml"

echo "==> Deploying health-checker app..."
kubectl apply -f "$ROOT_DIR/deploy/healthchecker/deployment.yaml"

echo "==> Adding prometheus-community Helm repo..."
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null 2>&1 || true
helm repo update

echo "==> Installing kube-prometheus-stack (Prometheus, Grafana, Alertmanager)..."
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  -f "$ROOT_DIR/deploy/prometheus/prometheus-values.yaml"

echo "==> Waiting for health-checker pod to become ready..."
kubectl wait --for=condition=Ready pods -l component=health-checker -n default --timeout=180s || true

echo "==> Waiting for monitoring pods to become ready..."
kubectl wait --for=condition=Ready pods --all -n monitoring --timeout=300s || true

echo "==> Status:"
kubectl get pods -n default
kubectl get pods -n monitoring

echo ""
echo "To access the health-checker API locally:"
echo "  kubectl port-forward -n default svc/health-checker-cluster-ip-service 8000:8000"
echo "  curl http://localhost:8000/api/summary"
echo ""
echo "To access Grafana:"
echo "  kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80"
echo "  open http://localhost:3000 (admin / changeme)"
