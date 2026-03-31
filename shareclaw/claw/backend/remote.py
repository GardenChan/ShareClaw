"""远程模式后端 —— 通过腾讯云 TAT 远程执行命令"""

import json
import logging
import time

from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException

from shareclaw.claw.backend.base import ClawBackend
from shareclaw.cloud.client import create_credential, create_lighthouse_client, create_tat_client
from shareclaw.cloud.lighthouse import check_instance_status
from shareclaw.cloud.tat import run_command, poll_invocation_task, wait_for_command_complete, run_command_and_wait
from shareclaw.claw.commands import (
    cmd_read_queue,
    cmd_write_queue,
    cmd_read_accounts,
    cmd_write_accounts,
    CMD_QUERY_STATUS,
    CMD_LOGIN,
    CMD_RESTART_GATEWAY,
    CMD_CHECK_GATEWAY,
    CMD_ENSURE_SHARECLAW_DIR,
)
from shareclaw.server.sse import sse_event

logger = logging.getLogger(__name__)


class RemoteBackend(ClawBackend):
    """
    远程模式后端。

    ShareClaw 独立部署，通过腾讯云 TAT 远程操作 Lighthouse 实例。
    支持管理单个 Lighthouse 实例。
    """

    def __init__(self, config: dict, instance_id: str = None, tat=None, lh_client=None):
        super().__init__(config)
        self.instance_id = instance_id or config["instance_ids"][0]
        self.region = config["region"]

        # 复用外部传入的云客户端，或创建新的
        if tat and lh_client:
            self.tat = tat
            self.lh_client = lh_client
        else:
            cred = create_credential(config)
            self.lh_client = create_lighthouse_client(cred, config)
            self.tat = create_tat_client(cred, config)

        # 确保远程 ~/.shareclaw 目录存在
        try:
            run_command_and_wait(self.tat, self.instance_id, CMD_ENSURE_SHARECLAW_DIR, timeout=10)
        except Exception:
            pass  # 目录可能已存在，忽略错误

    # ── 队列管理 ──────────────────────────────────────────

    def read_queue(self) -> list:
        try:
            result = run_command_and_wait(
                self.tat, self.instance_id, cmd_read_queue(), timeout=15
            )
            if result["task_status"] == "SUCCESS" and result["output"].strip():
                return json.loads(result["output"].strip())
        except (json.JSONDecodeError, Exception):
            pass
        return []

    def write_queue(self, queue: list) -> None:
        queue_json = json.dumps(queue, ensure_ascii=False)
        result = run_command_and_wait(
            self.tat, self.instance_id, cmd_write_queue(queue_json), timeout=15
        )
        if result["task_status"] != "SUCCESS":
            raise RuntimeError(f"写入队列失败: {result['output']}")

    # ── accounts.json 操作 ────────────────────────────────

    def read_accounts(self) -> list:
        try:
            result = run_command_and_wait(
                self.tat, self.instance_id, cmd_read_accounts(), timeout=15
            )
            if result["task_status"] == "SUCCESS" and result["output"].strip():
                return json.loads(result["output"].strip())
        except (json.JSONDecodeError, Exception):
            pass
        return []

    def write_accounts(self, accounts: list) -> None:
        accounts_json = json.dumps(accounts, ensure_ascii=False)
        result = run_command_and_wait(
            self.tat, self.instance_id, cmd_write_accounts(accounts_json), timeout=15
        )
        if result["task_status"] != "SUCCESS":
            raise RuntimeError(f"写入 accounts.json 失败: {result['output']}")

    # ── 状态查询 ──────────────────────────────────────────

    def query_status(self) -> dict:
        result = run_command_and_wait(
            self.tat, self.instance_id, CMD_QUERY_STATUS, timeout=30
        )
        if result["task_status"] != "SUCCESS":
            raise RuntimeError(f"查询状态失败: {result['output']}")

        output = result["output"]
        parts = output.split("---ACCOUNTS_SEPARATOR---")
        return {
            "config": parts[0].strip() if len(parts) > 0 else "",
            "accounts": parts[1].strip() if len(parts) > 1 else "[]",
        }

    # ── 登录 ──────────────────────────────────────────────

    def login(self):
        """
        通过 TAT 执行微信登录。

        Yields:
            str: SSE 事件
        """
        invocation_id = run_command(
            self.tat, self.instance_id, CMD_LOGIN, timeout=600
        )

        # 阶段 1：轮询直到输出中出现二维码
        qrcode_text = None
        start_time = time.time()
        max_wait_qrcode = 120

        while time.time() - start_time < max_wait_qrcode:
            task_info = poll_invocation_task(self.tat, invocation_id)

            if task_info:
                output = task_info["output"]

                if output and "使用微信扫描以下二维码" in output:
                    qrcode_text = output
                    break

                if task_info["task_status"] in ("FAILED", "TIMEOUT"):
                    raise RuntimeError(f"登录命令执行失败: {output}")

            time.sleep(3)

        if not qrcode_text:
            raise TimeoutError("等待二维码输出超时（120秒）")

        # 推送二维码
        yield sse_event("qrcode", {
            "stage": "qrcode",
            "message": "请扫描以下二维码登录微信",
            "data": qrcode_text,
        })

        # 阶段 2：等待扫码完成
        login_result = wait_for_command_complete(
            self.tat, invocation_id, max_wait=600
        )

        if login_result["task_status"] != "SUCCESS":
            raise RuntimeError(f"微信登录失败: {login_result['output']}")

        yield sse_event("progress", {
            "stage": "login_complete",
            "message": "微信登录成功",
            "data": login_result["output"],
        })

    # ── Gateway 管理 ──────────────────────────────────────

    def restart_gateway(self) -> None:
        result = run_command_and_wait(
            self.tat, self.instance_id, CMD_RESTART_GATEWAY, timeout=30
        )
        if result["task_status"] != "SUCCESS":
            raise RuntimeError(f"重启 gateway 失败: {result['output']}")

    def check_gateway(self) -> str:
        result = run_command_and_wait(
            self.tat, self.instance_id, CMD_CHECK_GATEWAY, timeout=15
        )
        return result["output"].strip()

    # ── 健康检查 ──────────────────────────────────────────

    def check_instance_health(self) -> bool:
        """检查 Lighthouse 实例是否健康（RUNNING 状态）"""
        try:
            check_instance_status(self.lh_client, self.instance_id)
            return True
        except RuntimeError as e:
            logger.warning(f"实例 {self.instance_id} 健康检查未通过: {e}")
            return False
        except TencentCloudSDKException as e:
            logger.error(
                "实例 %s 健康检查调用云 API 失败: code=%s, message=%s, request_id=%s",
                self.instance_id,
                getattr(e, "code", ""),
                getattr(e, "message", str(e)),
                getattr(e, "requestId", ""),
            )
            return False

    # ── 标识 ──────────────────────────────────────────────

    def get_instance_id(self) -> str:
        return self.instance_id