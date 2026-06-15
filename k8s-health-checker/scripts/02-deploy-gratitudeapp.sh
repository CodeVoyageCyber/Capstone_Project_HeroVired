#!/usr/bin/env bash
#
# scripts/02-deploy-gratitudeapp.sh
#
# Deploys the GratitudeApp microservices (client, api-gateway,
# entries/moods/stats services, files-service, postgres, ingress)
# onto the EKS cluster, using the existing Docker Hub images
# referenced in gratitude-k8s/*.yml.
#
# Prerequisites:
#   - scripts/01-provision-eks.sh has been run successfully
#   - kubectl is configured against the EKS cluster
#   - You have edited gratitude-k8s/database-secret.yml and
#     gratitude-k8s/openai-api-secret.yml with real values
#     (see docs/SECRETS.md)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
K8S_DIR="$ROOT_DIR/gratitude-k8s"

echo "==> Applying storage class, secrets, and config..."
kubectl apply -f "$K8S_DIR/storageclass-gp3-default.yml"
kubectl apply -f "$K8S_DIR/database-secret.yml"
kubectl apply -f "$K8S_DIR/postgres-init-config.yml"
kubectl apply -f "$K8S_DIR/openai-api-secret.yml"

echo "==> Deploying Postgres..."
kubectl apply -f "$K8S_DIR/database-persistent-volume-claim.yml"
kubectl apply -f "$K8S_DIR/postgres-deployment.yml"
kubectl apply -f "$K8S_DIR/postgres-cluster-ip-service.yml"

echo "==> Waiting for Postgres to become ready..."
kubectl wait --for=condition=Ready pods -l component=postgres --timeout=180s || true

echo "==> Deploying backend microservices..."
kubectl apply -f "$K8S_DIR/api-gateway-deployment.yml"
kubectl apply -f "$K8S_DIR/api-gateway-cluster-ip-service.yml"
kubectl apply -f "$K8S_DIR/entries-deployment.yml"
kubectl apply -f "$K8S_DIR/entries-cluster-ip-service.yml"
kubectl apply -f "$K8S_DIR/moods-api-deployment.yml"
kubectl apply -f "$K8S_DIR/moods-api-cluster-ip-service.yml"
kubectl apply -f "$K8S_DIR/moods-service-deployment.yml"
kubectl apply -f "$K8S_DIR/moods-service-cluster-ip-service.yml"
kubectl apply -f "$K8S_DIR/stats-api-deployment.yml"
kubectl apply -f "$K8S_DIR/stats-api-cluster-ip-service.yml"
kubectl apply -f "$K8S_DIR/stats-service-deployment.yml"
kubectl apply -f "$K8S_DIR/stats-service-cluster-ip-service.yml"
kubectl apply -f "$K8S_DIR/files-service-deployment.yml"
kubectl apply -f "$K8S_DIR/files-service-cluster-ip-service.yml"
kubectl apply -f "$K8S_DIR/server-deployment.yml"
kubectl apply -f "$K8S_DIR/server-cluster-ip-service.yml"

echo "==> Deploying frontend client..."
kubectl apply -f "$K8S_DIR/client-deployment.yml"
kubectl apply -f "$K8S_DIR/client-cluster-ip-service.yml"
kubectl apply -f "$K8S_DIR/client-service.yml"

echo "==> Applying ingress..."
kubectl apply -f "$K8S_DIR/ingress-service.yml"

echo "==> Running one-time DB migration job (creates 'moods' table if missing)..."
kubectl apply -f "$K8S_DIR/postgres-migrate-job.yml" || true

echo "==> Waiting for all GratitudeApp pods to become ready (this can take a few minutes)..."
kubectl wait --for=condition=Ready pods --all -n default --timeout=300s || true

echo "==> Status:"
kubectl get pods
echo ""
echo "==> Ingress / external address (may take a few minutes to provision an NLB):"
kubectl get ingress
kubectl get svc -n ingress-nginx
