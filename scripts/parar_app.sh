#!/usr/bin/env bash
# Para o servico ECS na hora (desiredCount -> 0), sem esperar o timeout
# automatico da Lambda de auto-stop.
set -euo pipefail

CLUSTER="respiratory-diseases-cluster"
SERVICE="respiratory-diseases-task-service-l0kgkxxb"
REGION="us-east-1"

echo "Desligando o servico ECS ($SERVICE)..."
aws ecs update-service \
  --cluster "$CLUSTER" \
  --service "$SERVICE" \
  --desired-count 0 \
  --region "$REGION" \
  --query '{status:service.status,desiredCount:service.desiredCount}' \
  --output json

echo "Servico desligado. O link publico continua o mesmo (a lambda porteira acorda o servico na proxima visita)."
