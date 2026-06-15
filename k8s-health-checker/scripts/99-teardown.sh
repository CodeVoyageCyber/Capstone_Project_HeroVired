#!/usr/bin/env bash
#
# scripts/99-teardown.sh
#
# Tears down everything: Helm releases, GratitudeApp + health-checker
# Kubernetes resources, and the EKS cluster + VPC via eksctl.
# Run this after taking your demo screenshots to avoid ongoing AWS
# charges (~$0.10/hr cluster fee + EC2 + NAT gateway + NLB from
# ingress-nginx).

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
K8S_DIR="$ROOT_DIR/gratitude-k8s"

echo "==> Uninstalling Helm releases (if cluster is reachable)..."
helm uninstall monitoring -n monitoring 2>/dev/null || true

echo "==> Deleting health-checker resources..."
kubectl delete -f "$ROOT_DIR/deploy/healthchecker/deployment.yaml" 2>/dev/null || true
kubectl delete -f "$ROOT_DIR/deploy/healthchecker/rbac.yaml" 2>/dev/null || true

echo "==> Deleting GratitudeApp resources..."
kubectl delete -f "$K8S_DIR/ingress-service.yml" 2>/dev/null || true
kubectl delete -f "$K8S_DIR/client-service.yml" 2>/dev/null || true
kubectl delete -f "$K8S_DIR/client-cluster-ip-service.yml" 2>/dev/null || true
kubectl delete -f "$K8S_DIR/client-deployment.yml" 2>/dev/null || true
kubectl delete -f "$K8S_DIR/server-cluster-ip-service.yml" 2>/dev/null || true
kubectl delete -f "$K8S_DIR/server-deployment.yml" 2>/dev/null || true
kubectl delete -f "$K8S_DIR/files-service-cluster-ip-service.yml" 2>/dev/null || true
kubectl delete -f "$K8S_DIR/files-service-deployment.yml" 2>/dev/null || true
kubectl delete -f "$K8S_DIR/stats-service-cluster-ip-service.yml" 2>/dev/null || true
kubectl delete -f "$K8S_DIR/stats-service-deployment.yml" 2>/dev/null || true
kubectl delete -f "$K8S_DIR/stats-api-cluster-ip-service.yml" 2>/dev/null || true
kubectl delete -f "$K8S_DIR/stats-api-deployment.yml" 2>/dev/null || true
kubectl delete -f "$K8S_DIR/moods-service-cluster-ip-service.yml" 2>/dev/null || true
kubectl delete -f "$K8S_DIR/moods-service-deployment.yml" 2>/dev/null || true
kubectl delete -f "$K8S_DIR/moods-api-cluster-ip-service.yml" 2>/dev/null || true
kubectl delete -f "$K8S_DIR/moods-api-deployment.yml" 2>/dev/null || true
kubectl delete -f "$K8S_DIR/entries-cluster-ip-service.yml" 2>/dev/null || true
kubectl delete -f "$K8S_DIR/entries-deployment.yml" 2>/dev/null || true
kubectl delete -f "$K8S_DIR/api-gateway-cluster-ip-service.yml" 2>/dev/null || true
kubectl delete -f "$K8S_DIR/api-gateway-deployment.yml" 2>/dev/null || true
kubectl delete -f "$K8S_DIR/postgres-cluster-ip-service.yml" 2>/dev/null || true
kubectl delete -f "$K8S_DIR/postgres-deployment.yml" 2>/dev/null || true
kubectl delete -f "$K8S_DIR/database-persistent-volume-claim.yml" 2>/dev/null || true
kubectl delete -f "$K8S_DIR/openai-api-secret.yml" 2>/dev/null || true
kubectl delete -f "$K8S_DIR/postgres-init-config.yml" 2>/dev/null || true
kubectl delete -f "$K8S_DIR/database-secret.yml" 2>/dev/null || true
kubectl delete -f "$K8S_DIR/storageclass-gp3-default.yml" 2>/dev/null || true

echo "==> Uninstalling ingress-nginx..."
helm uninstall ingress-nginx -n ingress-nginx 2>/dev/null || true

echo "==> Deleting EKS cluster via eksctl (this takes ~10-15 min)..."
eksctl delete cluster -f "$ROOT_DIR/eksctl/cluster.yaml"

echo "==> Done. All AWS resources for this project should now be removed."
echo "==> Double-check in the AWS console: EKS, EC2, VPC, NAT Gateways, ELB/NLB, EBS volumes, ECR."
