import importlib
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch


def _reload_handler():
    import scripts.lambda_wake.handler as handler_module
    importlib.reload(handler_module)
    return handler_module


def _patch_boto_clients(mock_boto_client, mock_ecs, mock_ec2):
    mock_boto_client.side_effect = lambda service, **kwargs: {
        "ecs": mock_ecs,
        "ec2": mock_ec2,
    }[service]


@patch("boto3.client")
def test_handler_starts_service_when_stopped(mock_boto_client, monkeypatch):
    monkeypatch.setenv("CLUSTER", "test-cluster")
    monkeypatch.setenv("SERVICE", "test-service")
    monkeypatch.setenv("REGION", "us-east-1")
    monkeypatch.setenv("PORT", "8501")

    mock_ecs, mock_ec2 = MagicMock(), MagicMock()
    _patch_boto_clients(mock_boto_client, mock_ecs, mock_ec2)
    mock_ecs.describe_services.return_value = {"services": [{"desiredCount": 0}]}
    mock_ecs.list_tasks.return_value = {"taskArns": []}

    handler = _reload_handler()
    response = handler.lambda_handler({}, None)

    mock_ecs.update_service.assert_called_once_with(
        cluster="test-cluster", service="test-service", desiredCount=1
    )
    assert response["statusCode"] == 200


@patch("boto3.client")
def test_handler_waits_without_restarting_when_already_scaling_up(mock_boto_client, monkeypatch):
    monkeypatch.setenv("CLUSTER", "test-cluster")
    monkeypatch.setenv("SERVICE", "test-service")
    monkeypatch.setenv("REGION", "us-east-1")
    monkeypatch.setenv("PORT", "8501")

    mock_ecs, mock_ec2 = MagicMock(), MagicMock()
    _patch_boto_clients(mock_boto_client, mock_ecs, mock_ec2)
    mock_ecs.describe_services.return_value = {"services": [{"desiredCount": 1}]}
    mock_ecs.list_tasks.return_value = {"taskArns": []}

    handler = _reload_handler()
    response = handler.lambda_handler({}, None)

    mock_ecs.update_service.assert_not_called()
    assert response["statusCode"] == 200


@patch("boto3.client")
def test_handler_redirects_when_task_ready(mock_boto_client, monkeypatch):
    monkeypatch.setenv("CLUSTER", "test-cluster")
    monkeypatch.setenv("SERVICE", "test-service")
    monkeypatch.setenv("REGION", "us-east-1")
    monkeypatch.setenv("PORT", "8501")

    mock_ecs, mock_ec2 = MagicMock(), MagicMock()
    _patch_boto_clients(mock_boto_client, mock_ecs, mock_ec2)

    started_at = datetime.now(timezone.utc) - timedelta(seconds=30)
    mock_ecs.describe_services.return_value = {"services": [{"desiredCount": 1}]}
    mock_ecs.list_tasks.return_value = {"taskArns": ["arn:aws:ecs:task/1"]}
    mock_ecs.describe_tasks.return_value = {
        "tasks": [
            {
                "lastStatus": "RUNNING",
                "startedAt": started_at,
                "attachments": [
                    {"details": [{"name": "networkInterfaceId", "value": "eni-123"}]}
                ],
            }
        ]
    }
    mock_ec2.describe_network_interfaces.return_value = {
        "NetworkInterfaces": [{"Association": {"PublicIp": "1.2.3.4"}}]
    }

    handler = _reload_handler()
    response = handler.lambda_handler({}, None)

    assert response["statusCode"] == 302
    assert response["headers"]["Location"] == "http://1.2.3.4:8501"
