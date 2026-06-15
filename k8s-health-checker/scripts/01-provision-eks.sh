#!/usr/bin/env bash
#
# scripts/01-provision-eks.sh
#
# Provisions the EKS cluster + VPC using Terraform and configures
# kubectl to point at it.
#
# Prerequisites:
#   - AWS CLI configured (aws configure) with credentials that can
#     create VPC/EKS/IAM resources
#   - Terraform >= 1.5
#   - kubectl

set -euo pipefail

TF_DIR="$(cd "$(dirname "$0")/../terraform" && pwd)"

cd "$TF_DIR"

if [ ! -f terraform.tfvars ]; then
  echo "==> No terraform.tfvars found. Copying from terraform.tfvars.example"
  cp terraform.tfvars.example terraform.tfvars
fi

echo "==> Initializing Terraform..."
terraform init

echo "==> Planning..."
terraform plan -out=tfplan

echo "==> Applying (this provisions a VPC + EKS cluster + node group, ~10-15 min)..."
terraform apply tfplan

echo "==> Configuring kubectl..."
CLUSTER_NAME=$(terraform output -raw cluster_name)
REGION=$(terraform output -raw region)
aws eks update-kubeconfig --region "$REGION" --name "$CLUSTER_NAME"

echo "==> Verifying cluster access..."
kubectl get nodes

echo "==> Done. Cluster '$CLUSTER_NAME' is ready."
