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
