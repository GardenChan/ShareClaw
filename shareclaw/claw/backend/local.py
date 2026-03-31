"""本地模式后端 —— 直接操作文件系统 + subprocess"""

import json
import os
import subprocess
import time

from shareclaw.claw.backend.base import ClawBackend
from shareclaw.server.sse import sse_event


class LocalBackend(ClawBackend):
    """
    本地模式后端。

    ShareClaw 与 OpenClaw 部署在同一台服务器上，
    直接通过文件系统读写 JSON 文件，通过 subprocess 执行命令。
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.openclaw_home = config["openclaw_home"]
        self.shareclaw_home = config["shareclaw_home"]

        # 确保 shareclaw 数据目录存在
        os.makedirs(self.shareclaw_home, exist_ok=True)

    @property
    def _accounts_path(self) -> str:
        """accounts.json 文件路径"""
        return os.path.join(self.openclaw_home, "openclaw-weixin", "accounts.json")

    @property
    def _queue_path(self) -> str:
        """accounts_queue.json 文件路径"""
        return os.path.join(self.shareclaw_home, "accounts_queue.json")

    @property
    def _openclaw_config_path(self) -> str:
        """openclaw.json 文件路径"""
        return os.path.join(self.openclaw_home, "openclaw.json")

    # ── 队列管理 ──────────────────────────────────────────

    def read_queue(self) -> list:
        if not os.path.exists(self._queue_path):
            return []
        try:
            with open(self._queue_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []

    def write_queue(self, queue: list) -> None:
        with open(self._queue_path, "w", encoding="utf-8") as f:
            json.dump(queue, f, ensure_ascii=False, indent=2)

    # ── accounts.json 操作 ────────────────────────────────

    def read_accounts(self) -> list:
        if not os.path.exists(self._accounts_path):
            return []
        try:
            with open(self._accounts_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []

    def write_accounts(self, accounts: list) -> None:
        # 确保目录存在
        os.makedirs(os.path.dirname(self._accounts_path), exist_ok=True)
        with open(self._accounts_path, "w", encoding="utf-8") as f:
            json.dump(accounts, f, ensure_ascii=False, indent=2)

    # ── 状态查询 ──────────────────────────────────────────

    def query_status(self) -> dict:
        # 读取 openclaw.json 的关键配置
        config_summary = ""
        if os.path.exists(self._openclaw_config_path):
            try:
                with open(self._openclaw_config_path, "r", encoding="utf-8") as f:
                    oc_config = json.load(f)
                # 只提取关键信息
                summary = {
                    "channels": oc_config.get("channels"),
                    "gateway": oc_config.get("gateway"),
                }
                config_summary = json.dumps(summary, ensure_ascii=False, indent=2)
            except (json.JSONDecodeError, IOError):
                config_summary = "{}"

        accounts = self.read_accounts()

        return {
            "config": config_summary,
            "accounts": json.dumps(accounts, ensure_ascii=False),
        }

    # ── 登录 ──────────────────────────────────────────────

    def login(self):
        """
        执行微信登录，通过 subprocess 运行 openclaw channels login。

        Yields:
            str: SSE 事件
        """
        cmd = "openclaw channels login --channel openclaw-weixin"

        process = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,  # 行缓冲
        )

        qrcode_found = False
        qrcode_yielded = False
        output_lines = []
        qrcode_lines = []
        collecting_qrcode = False
        start_time = time.time()

        try:
            for line in process.stdout:
                output_lines.append(line)

                # 检测二维码开始
                if "使用微信扫描以下二维码" in line and not qrcode_found:
                    qrcode_found = True
                    collecting_qrcode = True
                    qrcode_lines.append(line)
                    continue

                # 收集二维码文本行（二维码由特殊字符组成，遇到空行或非二维码内容时结束收集）
                if collecting_qrcode:
                    stripped = line.strip()
                    if stripped == "" and len(qrcode_lines) > 1:
                        # 空行标志二维码结束，立即推送
                        collecting_qrcode = False
                        qrcode_text = "".join(qrcode_lines)
                        qrcode_yielded = True
                        yield sse_event("qrcode", {
                            "stage": "qrcode",
                            "message": "请扫描以下二维码登录微信",
                            "data": qrcode_text,
                        })
                    else:
                        qrcode_lines.append(line)

                # 超时检查（10 分钟）
                if time.time() - start_time > 600:
                    process.kill()
                    raise TimeoutError("登录超时（600秒）")

            # 如果二维码收集中但进程已结束（没有遇到空行结束符），仍然推送
            if qrcode_found and not qrcode_yielded:
                qrcode_text = "".join(qrcode_lines)
                qrcode_yielded = True
                yield sse_event("qrcode", {
                    "stage": "qrcode",
                    "message": "请扫描以下二维码登录微信",
                    "data": qrcode_text,
                })

            process.wait()

            if not qrcode_found:
                raise RuntimeError(f"登录过程中未检测到二维码输出: {''.join(output_lines)}")

            if process.returncode != 0:
                raise RuntimeError(f"登录命令退出码: {process.returncode}")

            # 登录成功后，读取新的 accounts.json 获取新增的 account
            yield sse_event("progress", {
                "stage": "login_complete",
                "message": "微信登录成功",
                "data": "".join(output_lines[-5:]),  # 最后几行输出
            })

        except Exception:
            process.kill()
            raise
        finally:
            process.stdout.close()

    # ── Gateway 管理 ──────────────────────────────────────

    def restart_gateway(self) -> None:
        result = subprocess.run(
            ["systemctl", "--user", "restart", "openclaw-gateway"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"重启 gateway 失败: {result.stderr}")

    def check_gateway(self) -> str:
        result = subprocess.run(
            ["systemctl", "--user", "is-active", "openclaw-gateway"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.stdout.strip()

    # ── 标识 ──────────────────────────────────────────────

    def get_instance_id(self) -> str:
        return "local"
