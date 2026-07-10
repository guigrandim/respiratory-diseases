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
