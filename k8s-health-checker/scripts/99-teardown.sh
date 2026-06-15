#!/usr/bin/env bash
#
# scripts/99-teardown.sh
#
# Tears down everything: Helm releases, Kubernetes resources, and
# the EKS cluster + VPC via Terraform. Run this after taking your
# demo screenshots to avoid ongoing AWS charges (~$0.10/hr cluster
# fee + EC2 + NAT gateway).

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TF_DIR="$ROOT_DIR/terraform"

echo "==> Uninstalling Helm releases (if cluster is reachable)..."
helm uninstall monitoring -n monitoring 2>/dev/null || true

echo "==> Deleting Kubernetes resources (if cluster is reachable)..."
kubectl delete -f "$ROOT_DIR/deploy/k8s/deployment.yaml" 2>/dev/null || true
kubectl delete -f "$ROOT_DIR/deploy/k8s/rbac.yaml" 2>/dev/null || true

echo "==> Destroying Terraform-managed infrastructure (EKS, VPC, NAT, etc.)..."
cd "$TF_DIR"
terraform destroy -auto-approve

echo "==> Done. All AWS resources for this project should now be removed."
echo "==> Double-check in the AWS console: EKS, EC2, VPC, NAT Gateways, ECR (if you want to remove the image repo too)."
