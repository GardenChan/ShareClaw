"""本地模式后端 —— 直接操作文件系统 + subprocess"""

import json
import logging
import os
import subprocess
import time

from shareclaw.claw.backend.base import ClawBackend
from shareclaw.server.sse import sse_event

logger = logging.getLogger(__name__)


def _build_subprocess_env() -> dict:
    """
    构建 subprocess 使用的**最小**环境变量。

    关键发现 1：systemd 服务环境中继承的变量（如 NODE_PATH、NODE_OPTIONS 等）
    会干扰 openclaw 的插件发现机制，导致 "Unsupported channel" 错误。
    而使用 env -i（完全干净环境）+ bash -lc 手动执行则成功。

    关键发现 2：**不要**显式设置 OPENCLAW_HOME 环境变量。openclaw 在没有
    OPENCLAW_HOME 时能自动从 HOME 推导出正确的配置目录（~/.openclaw），
    但显式传入 OPENCLAW_HOME 会触发不同的配置路径解析逻辑，导致配置
    读取失败、插件发现失败，最终报 "Unsupported channel" 错误。
    让 bash login shell 从 .bashrc/.profile 构建环境后，openclaw 自行
    处理配置发现即可。

    关键发现 3：**必须传递 DBUS_SESSION_BUS_ADDRESS 和 XDG_RUNTIME_DIR**。
    systemctl --user 命令依赖这两个变量连接用户级 D-Bus session，
    缺少它们会导致 "Failed to connect to bus: No medium found" 错误，
    使得 restart_gateway / check_gateway 等操作失败。

    因此这里只传递最少必要变量（HOME、LANG 等）+ D-Bus 相关变量，
    让 bash login shell 从 .bashrc/.profile 重新构建完整的运行时环境，
    避免 systemd 残留变量的干扰。
    """
    home = os.environ.get("HOME", "/root")
    uid = os.getuid()
    env = {
        "HOME": home,
        "USER": os.environ.get("USER", "root"),
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "TERM": os.environ.get("TERM", "xterm-256color"),
    }

    # systemctl --user 依赖 D-Bus session 和 XDG_RUNTIME_DIR
    # 优先从当前环境继承，否则按 Linux 惯例构造默认值
    dbus_addr = os.environ.get("DBUS_SESSION_BUS_ADDRESS")
    if dbus_addr:
        env["DBUS_SESSION_BUS_ADDRESS"] = dbus_addr
    else:
        # systemd 默认的用户 bus 地址
        env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path=/run/user/{uid}/bus"

    xdg_runtime = os.environ.get("XDG_RUNTIME_DIR")
    if xdg_runtime:
        env["XDG_RUNTIME_DIR"] = xdg_runtime
    else:
        env["XDG_RUNTIME_DIR"] = f"/run/user/{uid}"

    # 注意：不传递 OPENCLAW_HOME，让 openclaw 自行从 HOME 推导配置目录
    logger.info(
        "subprocess 最小环境已构建, HOME=%s, XDG_RUNTIME_DIR=%s, DBUS=%s (OPENCLAW_HOME 不显式传递)",
        home, env.get("XDG_RUNTIME_DIR"), env.get("DBUS_SESSION_BUS_ADDRESS"),
    )

    return env


def _wrap_cmd_for_login_shell(cmd: str) -> list:
    """
    将命令包装为 bash login shell 执行。

    openclaw 通过 nvm + pnpm 全局安装，其 channel 插件（如 openclaw-weixin）
    的加载依赖 .bashrc/.profile 中 nvm/pnpm 的初始化脚本设置的完整 Node.js
    运行时环境。systemd 服务环境不会 source 这些脚本，导致插件无法被发现，
    报 "Unsupported channel" 错误。

    通过 bash -lc 执行命令，bash 会以 login shell 模式运行，自动 source
    /etc/profile、~/.profile、~/.bashrc 等初始化脚本，确保 nvm/pnpm
    正确初始化，openclaw 才能发现并加载扩展插件。
    """
    return ["bash", "-lc", cmd]


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
        self._subprocess_env = _build_subprocess_env()

        # 注意：不将 OPENCLAW_HOME 注入 subprocess 环境。
        # openclaw 在没有 OPENCLAW_HOME 时能自动从 HOME 推导配置目录，
        # 显式传入反而会触发不同的路径解析逻辑导致插件发现失败。
        logger.info("LocalBackend openclaw_home=%s (不注入 subprocess 环境)", self.openclaw_home)

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
        wrapped_cmd = _wrap_cmd_for_login_shell(cmd)

        # 记录调试信息，帮助排查 systemd 环境问题
        logger.info("执行登录命令: %s", wrapped_cmd)
        logger.info("subprocess OPENCLAW_HOME: %s", self._subprocess_env.get("OPENCLAW_HOME", ""))
        logger.info("subprocess HOME: %s", self._subprocess_env.get("HOME", ""))
        logger.info("subprocess cwd: %s", self.openclaw_home)

        process = subprocess.Popen(
            wrapped_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,  # 行缓冲
            env=self._subprocess_env,
            cwd=self.openclaw_home,
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
            env=self._subprocess_env,
        )
        if result.returncode != 0:
            raise RuntimeError(f"重启 gateway 失败: {result.stderr}")

    def check_gateway(self) -> str:
        result = subprocess.run(
            ["systemctl", "--user", "is-active", "openclaw-gateway"],
            capture_output=True,
            text=True,
            timeout=15,
            env=self._subprocess_env,
        )
        return result.stdout.strip()

    # ── 标识 ──────────────────────────────────────────────

    def get_instance_id(self) -> str:
        return "local"
