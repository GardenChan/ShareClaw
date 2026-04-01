"""
微信账号强隔离模块

开启强隔离后，每个新接入的微信号会自动：
1. 创建独立的 OpenClaw Agent（独立工作区、会话、记忆、人格）
2. 配置 binding 路由，将该 accountId 的消息路由到独立 Agent
3. 重启 gateway 使配置生效

关闭强隔离后，新接入的微信号走默认 agent（现有行为不变）。
"""

import json
import logging
import os
from typing import Optional

from shareclaw.claw.backend.base import ClawBackend

logger = logging.getLogger(__name__)


def make_agent_id(account_id: str) -> str:
    """
    根据 accountId 生成对应的 agentId。

    Args:
        account_id: 微信 accountId，如 "561b705dc7e0-im-bot"

    Returns:
        str: agentId，如 "wx-561b705dc7e0"
    """
    # 去掉 "-im-bot" 后缀，加上 "wx-" 前缀
    short = account_id.replace("-im-bot", "")
    return f"wx-{short}"


def setup_isolated_agent(backend: ClawBackend, account_id: str) -> dict:
    """
    为新接入的微信号创建独立的 Agent 并配置 binding。

    流程：
    1. 生成 agentId
    2. 执行 openclaw agents add 创建独立 Agent
    3. 添加 binding 将该 accountId 路由到该 Agent
    4. 重启 gateway

    Args:
        backend: 后端实例（local 或 remote）
        account_id: 新接入的微信 accountId

    Returns:
        dict: 包含 agent_id 和操作结果
    """
    from shareclaw.claw.commands import cmd_create_agent, cmd_add_binding, CMD_RESTART_GATEWAY

    agent_id = make_agent_id(account_id)

    logger.info(f"强隔离：为 account {account_id} 创建独立 Agent {agent_id}")

    result = {"agent_id": agent_id, "account_id": account_id, "steps": []}

    # Step 1: 创建独立 Agent
    try:
        _run_backend_command(backend, cmd_create_agent(agent_id), "create_agent", timeout=30)
        result["steps"].append({"step": "create_agent", "status": "ok"})
        logger.info(f"强隔离：Agent {agent_id} 创建成功")
    except Exception as e:
        # Agent 可能已存在，不视为致命错误
        msg = str(e)
        if "already exists" in msg.lower() or "已存在" in msg:
            result["steps"].append({"step": "create_agent", "status": "exists"})
            logger.info(f"强隔离：Agent {agent_id} 已存在，跳过创建")
        else:
            result["steps"].append({"step": "create_agent", "status": "error", "message": msg})
            logger.warning(f"强隔离：创建 Agent {agent_id} 失败: {e}")
            # 继续尝试添加 binding，Agent 可能之前已创建

    # Step 2: 添加 binding 路由
    try:
        _run_backend_command(backend, cmd_add_binding(agent_id, account_id), "add_binding", timeout=15)
        result["steps"].append({"step": "add_binding", "status": "ok"})
        logger.info(f"强隔离：binding {account_id} → {agent_id} 已添加")
    except Exception as e:
        result["steps"].append({"step": "add_binding", "status": "error", "message": str(e)})
        logger.error(f"强隔离：添加 binding 失败: {e}")

    return result


def teardown_isolated_agent(backend: ClawBackend, account_id: str) -> dict:
    """
    彻底清理被踢出账号的隔离 Agent。

    清理内容：
    1. 移除 binding 路由
    2. 从 openclaw.json 的 agents.list 中移除该 Agent
    3. 删除 Agent 的工作区和目录（~/.openclaw/workspace-wx-xxx, ~/.openclaw/agents/wx-xxx）

    Args:
        backend: 后端实例
        account_id: 被踢出的微信 accountId

    Returns:
        dict: 操作结果
    """
    from shareclaw.claw.commands import cmd_remove_binding, cmd_remove_agent, cmd_cleanup_agent_dirs

    agent_id = make_agent_id(account_id)

    logger.info(f"强隔离：彻底清理 account {account_id} 的 Agent {agent_id}")

    result = {"agent_id": agent_id, "account_id": account_id, "steps": []}

    # Step 1: 移除 binding
    try:
        _run_backend_command(backend, cmd_remove_binding(account_id), "remove_binding", timeout=15)
        result["steps"].append({"step": "remove_binding", "status": "ok"})
        logger.info(f"强隔离：binding {account_id} 已移除")
    except Exception as e:
        result["steps"].append({"step": "remove_binding", "status": "error", "message": str(e)})
        logger.warning(f"强隔离：移除 binding 失败: {e}")

    # Step 2: 从 agents.list 中移除
    try:
        _run_backend_command(backend, cmd_remove_agent(agent_id), "remove_agent", timeout=15)
        result["steps"].append({"step": "remove_agent", "status": "ok"})
        logger.info(f"强隔离：Agent {agent_id} 已从 agents.list 移除")
    except Exception as e:
        result["steps"].append({"step": "remove_agent", "status": "error", "message": str(e)})
        logger.warning(f"强隔离：从 agents.list 移除 Agent 失败: {e}")

    # Step 3: 删除工作区和 agent 目录
    try:
        _run_backend_command(backend, cmd_cleanup_agent_dirs(agent_id), "cleanup_dirs", timeout=15)
        result["steps"].append({"step": "cleanup_dirs", "status": "ok"})
        logger.info(f"强隔离：Agent {agent_id} 的工作区和目录已删除")
    except Exception as e:
        result["steps"].append({"step": "cleanup_dirs", "status": "error", "message": str(e)})
        logger.warning(f"强隔离：删除 Agent 目录失败: {e}")

    return result


def get_isolation_status(backend: ClawBackend) -> dict:
    """
    获取当前隔离状态信息。

    Returns:
        dict: 包含 bindings 和 agents 信息
    """
    from shareclaw.claw.commands import cmd_list_bindings, cmd_list_agents

    result = {"bindings": [], "agents": []}

    try:
        bindings_output = _run_backend_command(
            backend, cmd_list_bindings(), "list_bindings", timeout=15
        )
        result["bindings"] = json.loads(bindings_output) if bindings_output.strip() else []
    except Exception as e:
        logger.warning(f"获取 bindings 失败: {e}")

    try:
        agents_output = _run_backend_command(
            backend, cmd_list_agents(), "list_agents", timeout=15
        )
        result["agents"] = json.loads(agents_output) if agents_output.strip() else []
    except Exception as e:
        logger.warning(f"获取 agents 失败: {e}")

    return result


def _run_backend_command(backend: ClawBackend, command: str, step_name: str, timeout: int = 30) -> str:
    """
    通过后端执行命令，兼容 local 和 remote 模式。

    Args:
        backend: 后端实例
        command: 要执行的命令
        step_name: 步骤名称（用于日志）
        timeout: 超时时间

    Returns:
        str: 命令输出

    Raises:
        RuntimeError: 命令执行失败
    """
    from shareclaw.claw.backend.local import LocalBackend
    from shareclaw.claw.backend.remote import RemoteBackend

    if isinstance(backend, LocalBackend):
        return _run_local_command(command, step_name, timeout)
    elif isinstance(backend, RemoteBackend):
        return _run_remote_command(backend, command, step_name, timeout)
    else:
        raise RuntimeError(f"不支持的后端类型: {type(backend)}")


def _run_local_command(command: str, step_name: str, timeout: int) -> str:
    """本地模式执行命令"""
    import subprocess
    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"{step_name} 失败 (exit={result.returncode}): {result.stderr or result.stdout}")
    return result.stdout


def _run_remote_command(backend, command: str, step_name: str, timeout: int) -> str:
    """远程模式通过 TAT 执行命令"""
    from shareclaw.cloud.tat import run_command_and_wait

    result = run_command_and_wait(
        backend.tat, backend.instance_id, command, timeout=timeout
    )
    if result["task_status"] != "SUCCESS":
        raise RuntimeError(f"{step_name} 失败: {result['output']}")
    return result["output"]
