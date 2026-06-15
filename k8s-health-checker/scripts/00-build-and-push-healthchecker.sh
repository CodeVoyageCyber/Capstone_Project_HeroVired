#!/usr/bin/env bash
#
# scripts/00-build-and-push-healthchecker.sh
#
# Builds the health-checker Docker image and pushes it to a new (or
# existing) ECR repository. Prints the image URI to use in
# deploy/healthchecker/deployment.yaml.
#
# Prerequisites:
#   - AWS CLI configured
#   - Docker
#   - EKS cluster already provisioned (for region info), or set
#     AWS_REGION manually below.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_NAME="gratitude-health-checker"
AWS_REGION="${AWS_REGION:-us-east-1}"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${REPO_NAME}"

echo "==> Ensuring ECR repository '${REPO_NAME}' exists..."
aws ecr describe-repositories --repository-names "$REPO_NAME" --region "$AWS_REGION" >/dev/null 2>&1 \
  || aws ecr create-repository --repository-name "$REPO_NAME" --region "$AWS_REGION" >/dev/null

echo "==> Logging in to ECR..."
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo "==> Building image..."
docker build -t "${REPO_NAME}:latest" "$ROOT_DIR/healthchecker-app"

echo "==> Tagging and pushing to ${ECR_URI}:latest..."
docker tag "${REPO_NAME}:latest" "${ECR_URI}:latest"
docker push "${ECR_URI}:latest"

echo ""
echo "==> Done. Image pushed to:"
echo "    ${ECR_URI}:latest"
echo ""
echo "Update deploy/healthchecker/deployment.yaml's image field to:"
echo "    image: ${ECR_URI}:latest"
