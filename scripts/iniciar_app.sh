#!/usr/bin/env bash
# Liga o servico ECS (desiredCount 0 -> 1) e imprime o link publico quando a
# task ficar saudavel. O servico fica parado (custo zero) por padrao; a
# Lambda "respiratory-diseases-auto-stop" desliga de novo automaticamente
# depois de MAX_UPTIME_MINUTES (hoje 120min) a partir do start da task.
set -euo pipefail

CLUSTER="respiratory-diseases-cluster"
SERVICE="respiratory-diseases-task-service-l0kgkxxb"
REGION="us-east-1"
PORT=8501

echo "Ligando o servico ECS ($SERVICE)..."
aws ecs update-service \
  --cluster "$CLUSTER" \
  --service "$SERVICE" \
  --desired-count 1 \
  --region "$REGION" \
  --query '{status:service.status,desiredCount:service.desiredCount}' \
  --output text > /dev/null

echo "Aguardando o servico estabilizar (pode levar 1-2 min)..."
aws ecs wait services-stable --cluster "$CLUSTER" --services "$SERVICE" --region "$REGION"

TASK_ARN=$(aws ecs list-tasks --cluster "$CLUSTER" --service-name "$SERVICE" --region "$REGION" --query 'taskArns[0]' --output text)
ENI_ID=$(aws ecs describe-tasks --cluster "$CLUSTER" --tasks "$TASK_ARN" --region "$REGION" \
  --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value' --output text)
PUBLIC_IP=$(aws ec2 describe-network-interfaces --network-interface-ids "$ENI_ID" --region "$REGION" \
  --query 'NetworkInterfaces[0].Association.PublicIp' --output text)

echo ""
echo "App no ar: http://${PUBLIC_IP}:${PORT}"
echo "(desliga sozinho automaticamente apos o tempo limite configurado na Lambda de auto-stop)"
