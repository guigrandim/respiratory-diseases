"""Wake-on-request Lambda: turns the ECS service on for the first real
request and redirects the visitor to the running Streamlit task."""
import os
from datetime import datetime, timezone

import boto3

from .decision import decide
from .templates import redirect_response, wait_response

CLUSTER = os.environ["CLUSTER"]
SERVICE = os.environ["SERVICE"]
REGION = os.environ.get("REGION", "us-east-1")
PORT = int(os.environ.get("PORT", "8501"))

ecs = boto3.client("ecs", region_name=REGION)
ec2 = boto3.client("ec2", region_name=REGION)


def _desired_count():
    # desiredCount == 0 significa serviço hibernado (nenhuma task deve
    # estar rodando); é o sinal que decide() usa para saber se já pedimos
    # para escalar ou se este é o primeiro visitante desde a hibernação.
    resp = ecs.describe_services(cluster=CLUSTER, services=[SERVICE])
    return resp["services"][0]["desiredCount"]


def _tasks():
    # Lista as tasks atuais do serviço e busca o detalhe de cada uma
    # (status, horário de início, ENI) em uma segunda chamada.
    task_arns = ecs.list_tasks(cluster=CLUSTER, serviceName=SERVICE)["taskArns"]
    if not task_arns:
        return []
    return ecs.describe_tasks(cluster=CLUSTER, tasks=task_arns)["tasks"]


def _public_ip(task):
    # A API describe_tasks não devolve o IP público direto: é preciso achar
    # o ID da ENI (Elastic Network Interface) anexada à task dentro de
    # "attachments"/"details" e então consultar a ENI em si no EC2 para
    # pegar o IP público associado a ela.
    eni_id = next(
        detail["value"]
        for attachment in task["attachments"]
        for detail in attachment["details"]
        if detail["name"] == "networkInterfaceId"
    )
    eni = ec2.describe_network_interfaces(NetworkInterfaceIds=[eni_id])
    return eni["NetworkInterfaces"][0]["Association"]["PublicIp"]


def lambda_handler(event, context):
    # Ponto de entrada da Lambda: decide se precisa ligar o serviço, pedir
    # para o visitante esperar, ou redirecioná-lo para a task já rodando.
    tasks = _tasks()
    now = datetime.now(timezone.utc)
    action = decide(_desired_count(), tasks, now)

    if action == "start":
        # Primeiro visitante desde a hibernação: liga o serviço (1 task) e
        # mostra a página de espera.
        ecs.update_service(cluster=CLUSTER, service=SERVICE, desiredCount=1)
        return wait_response()

    if action == "wait":
        return wait_response()

    # action == "ready": existe uma task RUNNING e já aquecida.
    running_task = next(t for t in tasks if t.get("lastStatus") == "RUNNING")
    try:
        return redirect_response(_public_ip(running_task), PORT)
    except Exception:
        # Se por algum motivo não conseguimos o IP (ENI ainda não associada,
        # etc.), cai para a página de espera em vez de quebrar a resposta.
        return wait_response()
