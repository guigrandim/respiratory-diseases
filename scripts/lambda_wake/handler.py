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
    resp = ecs.describe_services(cluster=CLUSTER, services=[SERVICE])
    return resp["services"][0]["desiredCount"]


def _tasks():
    task_arns = ecs.list_tasks(cluster=CLUSTER, serviceName=SERVICE)["taskArns"]
    if not task_arns:
        return []
    return ecs.describe_tasks(cluster=CLUSTER, tasks=task_arns)["tasks"]


def _public_ip(task):
    eni_id = next(
        detail["value"]
        for attachment in task["attachments"]
        for detail in attachment["details"]
        if detail["name"] == "networkInterfaceId"
    )
    eni = ec2.describe_network_interfaces(NetworkInterfaceIds=[eni_id])
    return eni["NetworkInterfaces"][0]["Association"]["PublicIp"]


def lambda_handler(event, context):
    tasks = _tasks()
    now = datetime.now(timezone.utc)
    action = decide(_desired_count(), tasks, now)

    if action == "start":
        ecs.update_service(cluster=CLUSTER, service=SERVICE, desiredCount=1)
        return wait_response()

    if action == "wait":
        return wait_response()

    running_task = next(t for t in tasks if t.get("lastStatus") == "RUNNING")
    try:
        return redirect_response(_public_ip(running_task), PORT)
    except Exception:
        return wait_response()
