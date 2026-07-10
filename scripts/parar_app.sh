#!/usr/bin/env bash
# Para o servico ECS na hora (desiredCount -> 0), sem esperar o timeout
# automatico da Lambda de auto-stop.
set -euo pipefail

CLUSTER="respiratory-diseases-cluster"
SERVICE="respiratory-diseases-task-service-l0kgkxxb"
REGION="us-east-1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
README="$SCRIPT_DIR/../README.md"

echo "Desligando o servico ECS ($SERVICE)..."
aws ecs update-service \
  --cluster "$CLUSTER" \
  --service "$SERVICE" \
  --desired-count 0 \
  --region "$REGION" \
  --query '{status:service.status,desiredCount:service.desiredCount}' \
  --output json

if [ -f "$README" ]; then
  sed -i "s|^\*\*Link atual:\*\*.*|**Link atual:** offline no momento (última atualização: $(date '+%d/%m/%Y %H:%M %Z'))|" "$README"
  echo "README.md atualizado (link marcado como offline)."
fi
