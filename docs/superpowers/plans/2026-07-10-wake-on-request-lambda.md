# Lambda Porteira (Wake-on-Request) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the manual `iniciar_app.sh` start step with a public Lambda ("porteira") that wakes the ECS Fargate service on the first real request and redirects the visitor to the running Streamlit app, so the service stays hibernated (`desiredCount=0`, zero cost) until someone actually visits.

**Architecture:** A Python Lambda behind a public Function URL checks ECS service/task state on every hit. If the service is stopped, it calls `UpdateService(desiredCount=1)` and returns an auto-refreshing HTML "waking up" page. Once a task is `RUNNING` and past a short warm-up window, it looks up the task's public IP (via ENI) and returns an HTTP 302 redirect straight to `http://<ip>:8501` — so the browser talks directly to Fargate and Streamlit's WebSocket works unmodified. The existing time-based auto-stop Lambda is untouched.

**Tech Stack:** Python 3.12 (Lambda runtime), boto3, pytest + unittest.mock for tests, AWS CLI for deployment (IAM role, Lambda, Function URL).

---

## File Structure

- `scripts/lambda_wake/__init__.py` — empty, makes the directory a package for local imports/tests.
- `scripts/lambda_wake/decision.py` — pure logic: given ECS state, decide `"start"` / `"wait"` / `"ready"`. No AWS calls, fully unit-testable.
- `scripts/lambda_wake/templates.py` — builds the two possible Lambda responses (wait-page HTML, redirect). No AWS calls.
- `scripts/lambda_wake/handler.py` — `lambda_handler`, the only module that talks to `boto3` (ECS/EC2). Thin: fetches state, calls `decision.decide`, calls `templates.*`.
- `tests/test_decision.py`, `tests/test_templates.py`, `tests/test_handler.py` — pytest unit tests.
- `tests/__init__.py` — empty.
- `pytest.ini` — adds repo root to `pythonpath` so `scripts.lambda_wake.*` imports work.
- `requirements-dev.txt` — adds `pytest` (dev-only; not needed at Streamlit runtime, so kept out of `requirements.txt`/Docker image).
- Modify: `scripts/parar_app.sh` — remove the block that rewrites the README "Link atual" line to "offline".
- Delete: `scripts/iniciar_app.sh`.
- Modify: `README.md` — "Demo ao vivo" and "Deploy" sections.

---

### Task 1: Test tooling

**Files:**
- Create: `requirements-dev.txt`
- Create: `pytest.ini`

- [ ] **Step 1: Create `requirements-dev.txt`**

```
pytest>=8.0,<9
```

- [ ] **Step 2: Create `pytest.ini`**

```ini
[pytest]
pythonpath = .
```

- [ ] **Step 3: Install dev dependencies**

Run: `pip install -r requirements-dev.txt`
Expected: pytest installs successfully.

- [ ] **Step 4: Commit**

```bash
git add requirements-dev.txt pytest.ini
git commit -m "chore: add pytest for lambda_wake unit tests"
```

---

### Task 2: Pure decision logic (`decision.py`)

**Files:**
- Create: `scripts/lambda_wake/__init__.py`
- Create: `scripts/lambda_wake/decision.py`
- Test: `tests/__init__.py`
- Test: `tests/test_decision.py`

- [ ] **Step 1: Create empty package markers**

```bash
touch scripts/lambda_wake/__init__.py tests/__init__.py
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_decision.py`:

```python
from datetime import datetime, timedelta, timezone

from scripts.lambda_wake.decision import decide, find_running_task, is_warmed_up

NOW = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)


def test_decide_starts_service_when_stopped():
    assert decide(desired_count=0, tasks=[], now=NOW) == "start"


def test_decide_waits_when_already_scaling_up_with_no_task_yet():
    assert decide(desired_count=1, tasks=[], now=NOW) == "wait"


def test_decide_waits_when_task_running_but_not_warmed_up():
    tasks = [{"lastStatus": "RUNNING", "startedAt": NOW - timedelta(seconds=5)}]
    assert decide(desired_count=1, tasks=tasks, now=NOW) == "wait"


def test_decide_ready_when_task_running_and_warmed_up():
    tasks = [{"lastStatus": "RUNNING", "startedAt": NOW - timedelta(seconds=30)}]
    assert decide(desired_count=1, tasks=tasks, now=NOW) == "ready"


def test_decide_ignores_non_running_tasks():
    tasks = [{"lastStatus": "PENDING", "startedAt": NOW}]
    assert decide(desired_count=1, tasks=tasks, now=NOW) == "wait"


def test_find_running_task_returns_none_when_empty():
    assert find_running_task([]) is None


def test_find_running_task_skips_non_running():
    tasks = [{"lastStatus": "PENDING"}, {"lastStatus": "RUNNING", "startedAt": NOW}]
    assert find_running_task(tasks) == tasks[1]


def test_is_warmed_up_false_right_after_start():
    task = {"startedAt": NOW}
    assert is_warmed_up(task, NOW) is False


def test_is_warmed_up_true_after_threshold():
    task = {"startedAt": NOW - timedelta(seconds=20)}
    assert is_warmed_up(task, NOW) is True
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_decision.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.lambda_wake.decision'`

- [ ] **Step 4: Write minimal implementation**

Create `scripts/lambda_wake/decision.py`:

```python
"""Pure decision logic for the wake-on-request Lambda (no AWS I/O)."""

WARMUP_SECONDS = 20


def find_running_task(tasks):
    for task in tasks:
        if task.get("lastStatus") == "RUNNING":
            return task
    return None


def is_warmed_up(task, now, warmup_seconds=WARMUP_SECONDS):
    elapsed = (now - task["startedAt"]).total_seconds()
    return elapsed >= warmup_seconds


def decide(desired_count, tasks, now):
    """Returns "start", "wait", or "ready".

    "start" -> no task running and the service hasn't been asked to scale up
               yet; caller should call UpdateService(desiredCount=1).
    "wait"  -> a task is scaling up or still inside its warm-up window;
               caller should show the waiting page.
    "ready" -> a running, warmed-up task exists; caller should redirect to it.
    """
    running_task = find_running_task(tasks)
    if running_task is None:
        return "start" if desired_count == 0 else "wait"
    return "ready" if is_warmed_up(running_task, now) else "wait"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_decision.py -v`
Expected: 9 passed

- [ ] **Step 6: Commit**

```bash
git add scripts/lambda_wake/__init__.py tests/__init__.py scripts/lambda_wake/decision.py tests/test_decision.py
git commit -m "feat: add pure decision logic for wake-on-request lambda"
```

---

### Task 3: Response templates (`templates.py`)

**Files:**
- Create: `scripts/lambda_wake/templates.py`
- Test: `tests/test_templates.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_templates.py`:

```python
from scripts.lambda_wake.templates import redirect_response, wait_response


def test_wait_response_is_200_html_with_refresh_meta():
    resp = wait_response()
    assert resp["statusCode"] == 200
    assert "refresh" in resp["body"]
    assert resp["headers"]["Content-Type"].startswith("text/html")


def test_redirect_response_points_to_task_ip_and_port():
    resp = redirect_response("1.2.3.4", 8501)
    assert resp["statusCode"] == 302
    assert resp["headers"]["Location"] == "http://1.2.3.4:8501"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_templates.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.lambda_wake.templates'`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/lambda_wake/templates.py`:

```python
"""Builds the two possible HTTP responses the wake-on-request lambda returns."""

WAIT_PAGE_HTML = """<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="10">
<title>Iniciando a demo...</title>
<style>body { font-family: sans-serif; text-align: center; margin-top: 15%; }</style>
</head>
<body>
<h1>Iniciando a demo...</h1>
<p>O servico esta acordando, isso leva cerca de 1 a 2 minutos.</p>
<p>Esta pagina atualiza sozinha a cada 10 segundos.</p>
</body>
</html>"""


def wait_response():
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "text/html; charset=utf-8"},
        "body": WAIT_PAGE_HTML,
    }


def redirect_response(ip, port):
    return {
        "statusCode": 302,
        "headers": {"Location": f"http://{ip}:{port}"},
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_templates.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/lambda_wake/templates.py tests/test_templates.py
git commit -m "feat: add response templates for wake-on-request lambda"
```

---

### Task 4: Lambda handler (`handler.py`)

**Files:**
- Create: `scripts/lambda_wake/handler.py`
- Test: `tests/test_handler.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_handler.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_handler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.lambda_wake.handler'`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/lambda_wake/handler.py`:

```python
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
    return redirect_response(_public_ip(running_task), PORT)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_handler.py -v`
Expected: 3 passed

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: 14 passed (9 from Task 2 + 2 from Task 3 + 3 from Task 4)

- [ ] **Step 6: Commit**

```bash
git add scripts/lambda_wake/handler.py tests/test_handler.py
git commit -m "feat: wire ECS/EC2 calls into wake-on-request lambda handler"
```

---

### Task 5: IAM role for the wake Lambda

This task calls real AWS APIs. Run it in an environment with AWS CLI configured with credentials that can create IAM roles and policies (same environment used for `scripts/parar_app.sh` today).

**Note on shell state:** if each step below is run as a separate command invocation, exported variables (`$ACCOUNT_ID`, etc.) will NOT carry over — each step that needs a variable re-derives it inline so it's self-contained regardless of how the steps are run.

**Files:**
- None (infrastructure only, created directly via AWS CLI — matches how the rest of this project's AWS resources were created, per the existing `scripts/*.sh`).

- [ ] **Step 1: Get the current AWS account ID**

Run: `ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text) && echo "$ACCOUNT_ID"`
Expected: a 12-digit AWS account ID printed.

- [ ] **Step 2: Create the trust policy and the role**

```bash
cat > /tmp/wake-trust-policy.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {"Service": "lambda.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

aws iam create-role \
  --role-name respiratory-diseases-wake-role \
  --assume-role-policy-document file:///tmp/wake-trust-policy.json
```

Expected: JSON output describing the new role, `RoleName: respiratory-diseases-wake-role`.

- [ ] **Step 3: Attach the minimal permissions policy**

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION="us-east-1"
CLUSTER="respiratory-diseases-cluster"
SERVICE="respiratory-diseases-task-service-l0kgkxxb"

cat > /tmp/wake-permissions-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "ecs:ListTasks",
      "Resource": "*",
      "Condition": {
        "ArnEquals": {
          "ecs:cluster": "arn:aws:ecs:${REGION}:${ACCOUNT_ID}:cluster/${CLUSTER}"
        }
      }
    },
    {
      "Effect": "Allow",
      "Action": [
        "ecs:DescribeServices",
        "ecs:UpdateService",
        "ecs:DescribeTasks"
      ],
      "Resource": [
        "arn:aws:ecs:${REGION}:${ACCOUNT_ID}:service/${CLUSTER}/${SERVICE}",
        "arn:aws:ecs:${REGION}:${ACCOUNT_ID}:task/${CLUSTER}/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": "ec2:DescribeNetworkInterfaces",
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:${REGION}:${ACCOUNT_ID}:*"
    }
  ]
}
EOF

aws iam put-role-policy \
  --role-name respiratory-diseases-wake-role \
  --policy-name respiratory-diseases-wake-permissions \
  --policy-document file:///tmp/wake-permissions-policy.json
```

Expected: no output on success (put-role-policy is silent).

Notes (corrected during execution, 2026-07-10):
- `ec2:DescribeNetworkInterfaces` doesn't support resource-level restriction, hence `Resource: "*"` for that statement only — it's a read-only, account-wide-safe action.
- `ecs:ListTasks` also doesn't support resource-level restriction to a `service`/`task` ARN the way `DescribeServices`/`UpdateService`/`DescribeTasks` do — attempting that produces `AccessDeniedException ... on resource: arn:...:container-instance/<cluster>/*` even though no container-instance ARN was referenced. The correct pattern (per AWS's own ECS IAM examples) is `Resource: "*"` combined with an `ecs:cluster` ArnEquals condition scoping it to the one cluster.

- [ ] **Step 4: Confirm the role is ready**

Run: `aws iam get-role --role-name respiratory-diseases-wake-role --query 'Role.Arn' --output text`
Expected: prints `arn:aws:iam::<ACCOUNT_ID>:role/respiratory-diseases-wake-role`. This ARN is deterministic (role name is fixed) — Task 6 re-derives it with `aws iam get-role`, no need to pass it manually.

No commit for this task (no repo files changed).

---

### Task 6: Package and deploy the Lambda + Function URL

Also real AWS calls. Continue in the same AWS-CLI-configured environment as Task 5.

**Note on shell state:** as in Task 5, each step below re-derives any variable it needs (via `aws ... get-...` lookups) instead of assuming an earlier step's export is still in scope.

**Files:**
- None (deployment only).

- [ ] **Step 1: Zip the handler code**

`handler.py` uses relative imports (`from .decision import decide`), so it must be deployed as a real package, not as flat top-level files — a flat zip produces `Runtime.ImportModuleError: attempted relative import with no known parent package` at cold start. Zip the whole `lambda_wake` directory (including `__init__.py`), preserving the folder structure, and make sure no `__pycache__` directory sneaks in:

```bash
find scripts/lambda_wake -name __pycache__ -type d -exec rm -rf {} +
cd scripts
zip -r /tmp/wake-lambda.zip lambda_wake -x '*__pycache__*'
cd -
```

(On Windows without `zip`, `Compress-Archive -Path scripts\lambda_wake -DestinationPath wake-lambda.zip -Force` from PowerShell produces the same layout — verify with `Expand-Archive` that it only contains `lambda_wake/{__init__.py,decision.py,handler.py,templates.py}`, no `__pycache__`.)

Expected: `/tmp/wake-lambda.zip` created, containing a `lambda_wake/` folder with the three `.py` files plus `__init__.py` inside it.

- [ ] **Step 2: Create the Lambda function**

Wait ~10 seconds after Task 5 for IAM role propagation before running this. Because the zip preserves the `lambda_wake/` package, `--handler` must reference the package path, not just `handler.lambda_handler`:

```bash
ROLE_ARN=$(aws iam get-role --role-name respiratory-diseases-wake-role --query 'Role.Arn' --output text)
REGION="us-east-1"
CLUSTER="respiratory-diseases-cluster"
SERVICE="respiratory-diseases-task-service-l0kgkxxb"

aws lambda create-function \
  --function-name respiratory-diseases-wake \
  --runtime python3.12 \
  --role "$ROLE_ARN" \
  --handler lambda_wake.handler.lambda_handler \
  --timeout 10 \
  --memory-size 128 \
  --zip-file fileb:///tmp/wake-lambda.zip \
  --environment "Variables={CLUSTER=${CLUSTER},SERVICE=${SERVICE},REGION=${REGION},PORT=8501}" \
  --region "$REGION"
```

Expected: JSON output with `FunctionName: respiratory-diseases-wake` and `State: Active` (or `Pending`, then check with `aws lambda get-function --function-name respiratory-diseases-wake`).

Sanity check before moving on — invoke it directly (bypasses the Function URL/HTTP layer entirely, isolating "does the code run" from "is the URL reachable"):

```bash
aws lambda invoke --function-name respiratory-diseases-wake --region us-east-1 /tmp/out.json --log-type Tail --query 'LogResult' --output text | base64 -d
cat /tmp/out.json
```

Expected: no `Runtime.ImportModuleError` or `AccessDeniedException` in the log tail; `/tmp/out.json` contains a `{"statusCode": 200, ...}` wait-page response (or a 302 if a task happens to already be running/warm).

- [ ] **Step 3: Cap concurrency to avoid overlapping start races (best-effort)**

```bash
aws lambda put-function-concurrency \
  --function-name respiratory-diseases-wake \
  --reserved-concurrent-executions 1 \
  --region us-east-1
```

Expected: JSON confirming `ReservedConcurrentExecutions: 1`.

This can fail with `InvalidParameterValueException: ... decreases account's UnreservedConcurrentExecution below its minimum value of [10]` on accounts still at the default 10-execution account-wide concurrency limit (check with `aws lambda get-account-settings --query AccountLimit`). If so, skip this step — it's a race-condition safety net, not required for correctness (repeated `ecs:UpdateService(desiredCount=1)` calls are idempotent), and raising the account limit requires an AWS Support request.

- [ ] **Step 4: Create the public Function URL**

```bash
aws lambda create-function-url-config \
  --function-name respiratory-diseases-wake \
  --auth-type NONE \
  --region us-east-1
```

Expected: JSON with a `FunctionUrl` like `https://<id>.lambda-url.us-east-1.on.aws/`. This value is also retrievable later with `aws lambda get-function-url-config --function-name respiratory-diseases-wake --query FunctionUrl --output text` — Task 8/9 use that lookup instead of relying on this step's output being remembered.

- [ ] **Step 5: Allow public invocation via the Function URL**

Since October 2025, AWS requires **both** `lambda:InvokeFunctionUrl` (scoped to the Function URL's `NONE` auth type) **and** a plain `lambda:InvokeFunction` grant — granting only the first now still produces `403 Forbidden {"Message":"Forbidden. For troubleshooting..."}` at the Function URL itself (no invocation, nothing in CloudWatch Logs, so it's easy to mistake for a DNS/network issue). The `--function-url-auth-type` flag is rejected on `InvokeFunction` (`FunctionUrlAuthType is only supported for lambda:InvokeFunctionUrl action`), so the second statement has no condition — it's a broader public grant, but no broader in practice than what visiting the public URL already allows (the "fora de escopo" no-auth trade-off the design doc already accepts):

```bash
aws lambda add-permission \
  --function-name respiratory-diseases-wake \
  --statement-id FunctionURLAllowPublicAccess \
  --action lambda:InvokeFunctionUrl \
  --principal "*" \
  --function-url-auth-type NONE \
  --region us-east-1

aws lambda add-permission \
  --function-name respiratory-diseases-wake \
  --statement-id FunctionURLAllowPublicInvoke \
  --action lambda:InvokeFunction \
  --principal "*" \
  --region us-east-1
```

Expected: JSON confirming each permission statement was added (two separate calls, two separate `Sid`s).

- [ ] **Step 6: Smoke test while the ECS service is stopped**

```bash
FUNCTION_URL=$(aws lambda get-function-url-config --function-name respiratory-diseases-wake --query FunctionUrl --output text --region us-east-1)
curl -s "$FUNCTION_URL"
aws ecs describe-services --cluster respiratory-diseases-cluster --services respiratory-diseases-task-service-l0kgkxxb --query 'services[0].desiredCount' --output text --region us-east-1
```

Expected: HTML containing `Iniciando a demo...` and `<meta http-equiv="refresh" content="10">`, then `1` printed for `desiredCount` (the curl call above already triggered the start).

No commit for this task (no repo files changed).

---

### Task 7: Remove the manual start script, trim the stop script

**Files:**
- Delete: `scripts/iniciar_app.sh`
- Modify: `scripts/parar_app.sh`

- [ ] **Step 1: Delete the start script**

```bash
git rm scripts/iniciar_app.sh
```

- [ ] **Step 2: Edit `scripts/parar_app.sh` to drop the README "offline" rewrite**

Current end of the file (`scripts/parar_app.sh:9-24`):

```bash
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
```

Replace with:

```bash
echo "Desligando o servico ECS ($SERVICE)..."
aws ecs update-service \
  --cluster "$CLUSTER" \
  --service "$SERVICE" \
  --desired-count 0 \
  --region "$REGION" \
  --query '{status:service.status,desiredCount:service.desiredCount}' \
  --output json

echo "Servico desligado. O link publico continua o mesmo (a lambda porteira acorda o servico na proxima visita)."
```

Also remove the now-unused `SCRIPT_DIR`/`README` variable lines and update the header comment (`scripts/parar_app.sh:1-4`) to drop the mention of the auto-stop Lambda timing if it now reads oddly next to the new comment — keep it, that part is still accurate.

- [ ] **Step 3: Verify the script is still valid bash**

Run: `bash -n scripts/parar_app.sh`
Expected: no output (syntax OK).

- [ ] **Step 4: Commit**

```bash
git add scripts/iniciar_app.sh scripts/parar_app.sh
git commit -m "chore: drop manual start script, stop rewriting README link on stop"
```

---

### Task 8: Update README

**Files:**
- Modify: `README.md:15-23` (Demo ao vivo)
- Modify: `README.md:108-126` (Deploy)

- [ ] **Step 1: Look up the Function URL**

```bash
aws lambda get-function-url-config --function-name respiratory-diseases-wake --query FunctionUrl --output text --region us-east-1
```

Expected: prints the URL created in Task 6, Step 4 (e.g. `https://abc123xyz.lambda-url.us-east-1.on.aws/`). Use it in place of `<FUNCTION_URL>` below.

- [ ] **Step 2: Replace the "Demo ao vivo" section**

Current (`README.md:15-23`):

```markdown
## Demo ao vivo

Este projeto usa *scale-to-zero* para reduzir custo — o serviço ECS fica
desligado por padrão (veja a seção "Deploy" abaixo).

**Link atual:** nenhuma instância ativa no momento

Para ativar uma instância de demonstração, [me contate](mailto:gui.grandim@gmail.com)
ou siga as instruções de deploy abaixo para rodar você mesmo.
```

Replace with (substitute `<FUNCTION_URL>` with the URL printed in Step 1 above):

```markdown
## Demo ao vivo

Este projeto usa *scale-to-zero* — o serviço ECS fica desligado por padrão e
acorda sozinho na primeira visita (veja a seção "Deploy" abaixo).

**Link:** <FUNCTION_URL>

Se o serviço estiver hibernando, a primeira visita mostra uma página de
"iniciando..." por ~1-2 minutos enquanto o ECS sobe, depois redireciona
automaticamente para o app. Esse link é permanente — não muda mais a cada
deploy.
```

- [ ] **Step 3: Replace the "Deploy" section**

Current (`README.md:108-126`):

```markdown
## Deploy (ECS Fargate) — liga sob demanda

O app roda em um serviço ECS Fargate (`respiratory-diseases-cluster` /
`respiratory-diseases-task-service-l0kgkxxb`), mas **fica parado por padrão**
(`desiredCount=0`) para não gerar custo continuo — é um projeto de
portfólio, sem tráfego constante.

- **Ligar**: `scripts/iniciar_app.sh` — sobe o serviço, espera a task ficar
  saudável e imprime o link público (IP direto, sem load balancer — muda a
  cada start).
- **Desligar na hora**: `scripts/parar_app.sh`.
- **Auto-stop**: uma função Lambda (`respiratory-diseases-auto-stop`),
  disparada a cada 10 minutos por uma regra do EventBridge, derruba o
  serviço automaticamente depois de 2h de uptime (`MAX_UPTIME_MINUTES`, env
  var da Lambda) — não é detecção de tráfego (o serviço não tem load
  balancer para medir requisições), é um limite de tempo de sessão. Ambos os
  scripts e a Lambda usam apenas `ecs:UpdateService` na task definition e no
  serviço já existentes; nenhuma outra configuração (porta, imagem, roles do
  container) muda.
```

Replace with:

```markdown
## Deploy (ECS Fargate) — liga sozinho sob demanda

O app roda em um serviço ECS Fargate (`respiratory-diseases-cluster` /
`respiratory-diseases-task-service-l0kgkxxb`), mas **fica parado por padrão**
(`desiredCount=0`) para não gerar custo continuo — é um projeto de
portfólio, sem tráfego constante.

- **Ligar**: automático. Uma Lambda pública ("porteira",
  `respiratory-diseases-wake`, código em `scripts/lambda_wake/`) é o link
  fixo do projeto. Ao receber uma requisição, ela confere o estado do
  serviço ECS; se estiver parado, chama `ecs:UpdateService` para subir e
  devolve uma página HTML que se auto-atualiza a cada ~10s; quando a task
  está `RUNNING` e passou de uma janela de warm-up, devolve um redirect 302
  direto para o IP público da task (`http://<ip>:8501`) — dali em diante o
  navegador fala direto com o Fargate, sem a Lambda no meio, então o
  WebSocket do Streamlit funciona normalmente.
- **Desligar na hora**: `scripts/parar_app.sh`.
- **Auto-stop**: uma função Lambda (`respiratory-diseases-auto-stop`),
  disparada a cada 10 minutos por uma regra do EventBridge, derruba o
  serviço automaticamente depois de 2h de uptime (`MAX_UPTIME_MINUTES`, env
  var da Lambda) — não é detecção de tráfego, é um limite de tempo de
  sessão.
- Nenhum ALB/NLB é usado (custo fixo extra não valeria a pena para o volume
  de tráfego deste projeto) — a porteira usa só a Function URL nativa da
  Lambda.
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document the wake-on-request lambda in place of the manual start script"
```

---

### Task 9: End-to-end verification against the live Function URL

**Files:**
- None (manual verification only).

**Note on shell state:** each step re-derives `FUNCTION_URL` via `aws lambda get-function-url-config` rather than assuming an earlier step's export carried over.

- [ ] **Step 1: Confirm the service is stopped**

Run: `aws ecs describe-services --cluster respiratory-diseases-cluster --services respiratory-diseases-task-service-l0kgkxxb --query 'services[0].desiredCount' --output text --region us-east-1`
Expected: `0`

- [ ] **Step 2: Hit the Function URL and confirm the wait page**

```bash
FUNCTION_URL=$(aws lambda get-function-url-config --function-name respiratory-diseases-wake --query FunctionUrl --output text --region us-east-1)
curl -s "$FUNCTION_URL" | grep -o 'Iniciando a demo'
```

Expected: `Iniciando a demo`

- [ ] **Step 3: Poll until redirected**

```bash
FUNCTION_URL=$(aws lambda get-function-url-config --function-name respiratory-diseases-wake --query FunctionUrl --output text --region us-east-1)
for i in $(seq 1 20); do
  STATUS=$(curl -s -o /dev/null -w '%{http_code}' "$FUNCTION_URL")
  echo "attempt $i: HTTP $STATUS"
  [ "$STATUS" = "302" ] && break
  sleep 10
done
```

Expected: eventually prints `attempt N: HTTP 302` within ~2 minutes.

- [ ] **Step 4: Confirm the redirect target serves Streamlit**

```bash
FUNCTION_URL=$(aws lambda get-function-url-config --function-name respiratory-diseases-wake --query FunctionUrl --output text --region us-east-1)
LOCATION=$(curl -s -D - -o /dev/null "$FUNCTION_URL" | grep -i '^location:' | tr -d '\r' | cut -d' ' -f2)
curl -s "$LOCATION" | grep -o '<title>[^<]*</title>'
```

Expected: prints the Streamlit page's `<title>` tag (confirms the app is actually serving on that redirect target, not just that ECS reports `RUNNING`).

- [ ] **Step 5: Clean up — stop the service**

Run: `bash scripts/parar_app.sh`
Expected: prints `Servico desligado...`, `desiredCount` back to `0`.

No commit for this task (verification only).
