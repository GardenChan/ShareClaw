"""TAT 命令执行模块"""

import base64
import time

from tencentcloud.tat.v20201028 import models as tat_models


def run_command(tat, instance_id, command, timeout=60, username="root"):
    """
    通过 TAT RunCommand 在 Lighthouse 上执行命令

    Args:
        tat: TAT 客户端
        instance_id: 实例 ID
        command: 要执行的 Shell 命令
        timeout: 命令超时时间（秒）
        username: 执行用户

    Returns:
        str: InvocationId
    """
    req = tat_models.RunCommandRequest()
    req.Content = base64.b64encode(command.encode("utf-8")).decode("utf-8")
    req.InstanceIds = [instance_id]
    req.CommandType = "SHELL"
    req.Timeout = timeout
    req.Username = username

    resp = tat.RunCommand(req)
    return resp.InvocationId


def poll_invocation_task(tat, invocation_id):
    """
    查询一次 InvocationTask 的状态和输出

    Args:
        tat: TAT 客户端
        invocation_id: 调用 ID

    Returns:
        dict: 包含 output, task_status, exit_code 的结果，如果还没有 task 信息则返回 None
    """
    req = tat_models.DescribeInvocationTasksRequest()
    req.InvocationTaskIds = []
    req.Filters = [
        {"Name": "invocation-id", "Values": [invocation_id]}
    ]

    resp = tat.DescribeInvocationTasks(req)
    tasks = resp.InvocationTaskSet

    if not tasks:
        return None

    task = tasks[0]
    output = task.TaskResult.Output if task.TaskResult else ""
    if output:
        output = base64.b64decode(output).decode("utf-8", errors="replace")

    return {
        "output": output,
        "task_status": task.TaskStatus,
        "exit_code": task.TaskResult.ExitCode if task.TaskResult else None,
    }


def wait_for_command_complete(tat, invocation_id, poll_interval=2, max_wait=600):
    """
    轮询等待命令执行完成

    Args:
        tat: TAT 客户端
        invocation_id: 调用 ID
        poll_interval: 轮询间隔（秒）
        max_wait: 最大等待时间（秒）

    Returns:
        dict: 包含 output, task_status, exit_code 的结果

    Raises:
        TimeoutError: 等待超时
    """
    start_time = time.time()

    while time.time() - start_time < max_wait:
        result = poll_invocation_task(tat, invocation_id)

        if result and result["task_status"] in ("SUCCESS", "FAILED", "TIMEOUT"):
            return result

        time.sleep(poll_interval)

    raise TimeoutError(f"等待命令执行超时（{max_wait}秒），InvocationId: {invocation_id}")


def run_command_and_wait(tat, instance_id, command, timeout=60, username="root"):
    """
    执行命令并等待完成，返回输出

    Args:
        tat: TAT 客户端
        instance_id: 实例 ID
        command: 要执行的 Shell 命令
        timeout: 命令超时时间（秒）
        username: 执行用户

    Returns:
        dict: 包含 output, task_status, exit_code 的结果
    """
    invocation_id = run_command(tat, instance_id, command, timeout=timeout, username=username)
    return wait_for_command_complete(tat, invocation_id, max_wait=timeout + 30)
