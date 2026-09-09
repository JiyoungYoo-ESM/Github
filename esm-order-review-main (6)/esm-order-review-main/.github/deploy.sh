#!/usr/bin/env bash
# Build both images, push to the env's ECR repos as :latest (+ :<sha>), then
# force a new ECS deployment. Shared by the deploy-dev / deploy-prd jobs.
set -euo pipefail

ENVIRONMENT="$1"
REG="$ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com"
SHA="${GITHUB_SHA::12}"
BE="$REG/sk-$ENVIRONMENT-an2-ecr-esm-backend"
FE="$REG/sk-$ENVIRONMENT-an2-ecr-esm-frontend"
CLUSTER="sk-$ENVIRONMENT-an2-ecs-cls-esm"
SERVICES=("sk-$ENVIRONMENT-an2-ecs-svc-esm" "sk-$ENVIRONMENT-an2-ecs-svc-worker-esm")

docker build -f ESM_SCM8/Dockerfile.backend  -t "$BE:latest" -t "$BE:$SHA" ESM_SCM8
docker build -f ESM_SCM8/frontend/Dockerfile -t "$FE:latest" -t "$FE:$SHA" ESM_SCM8/frontend
docker push "$BE:latest"; docker push "$BE:$SHA"
docker push "$FE:latest"; docker push "$FE:$SHA"

# Redeploy only services that already exist (infra is deployed locally with cdk).
for SERVICE in "${SERVICES[@]}"; do
  status="$(aws ecs describe-services --cluster "$CLUSTER" --services "$SERVICE" \
    --query 'services[0].status' --output text 2>/dev/null || echo MISSING)"
  if [ "$status" = "ACTIVE" ]; then
    update_args=(--cluster "$CLUSTER" --service "$SERVICE" --force-new-deployment)
    # Keep the production analysis service at two one-process workers even when
    # an application-only deploy runs without a separate CDK deployment.
    if [ "$ENVIRONMENT" = "prd" ] && [[ "$SERVICE" == *-worker-esm ]]; then
      update_args+=(--desired-count 2)
    fi
    aws ecs update-service "${update_args[@]}" >/dev/null
    aws ecs wait services-stable --cluster "$CLUSTER" --services "$SERVICE"
    echo "Redeployed $SERVICE."
  else
    echo "Service $SERVICE not ACTIVE (status=$status) — images pushed; deploy infra locally with cdk."
  fi
done
