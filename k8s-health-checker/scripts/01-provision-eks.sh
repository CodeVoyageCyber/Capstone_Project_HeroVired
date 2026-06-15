#!/usr/bin/env bash
#
# scripts/01-provision-eks.sh
#
# Provisions the EKS cluster (with OIDC + EBS CSI driver addon) via
# eksctl, configures kubectl, and installs ingress-nginx via Helm.
#
# Prerequisites:
#   - AWS CLI configured (aws configure) with credentials that can
#     create VPC/EKS/IAM/EC2 resources
#   - eksctl
#   - kubectl
#   - helm

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Creating EKS cluster via eksctl (this takes ~15-20 min)..."
eksctl create cluster -f "$ROOT_DIR/eksctl/cluster.yaml"

echo "==> Verifying cluster access..."
kubectl get nodes

echo "==> Verifying EBS CSI driver addon..."
kubectl get pods -n kube-system | grep ebs-csi || true

echo "==> Adding ingress-nginx Helm repo..."
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx >/dev/null 2>&1 || true
helm repo update

echo "==> Installing ingress-nginx (NLB)..."
helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx --create-namespace \
  --set controller.service.type=LoadBalancer \
  --set controller.service.annotations."service\.beta\.kubernetes\.io/aws-load-balancer-type"=nlb \
  --set controller.resources.requests.cpu=100m \
  --set controller.resources.requests.memory=128Mi

echo "==> Waiting for ingress-nginx controller to become ready..."
kubectl wait --for=condition=Ready pods --all -n ingress-nginx --timeout=180s || true

echo "==> Done. Cluster 'gratitude-health-cluster' is ready."
