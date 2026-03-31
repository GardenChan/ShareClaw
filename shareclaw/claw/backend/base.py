"""后端抽象基类 —— 定义本地/远程后端的统一接口"""

from abc import ABC, abstractmethod
from typing import Generator, List, Optional


class ClawBackend(ABC):
    """
    后端抽象基类。

    本地模式 (LocalBackend)：直接操作文件系统 + subprocess
    远程模式 (RemoteBackend)：通过腾讯云 TAT 远程执行命令
    """

    def __init__(self, config: dict):
        self.config = config
        self.max_queue_size = config.get("max_queue_size", 6)

    # ── 队列管理 ──────────────────────────────────────────

    @abstractmethod
    def read_queue(self) -> list:
        """
        读取 accounts_queue.json 队列

        Returns:
            list: 队列数组，每个元素为 {"account": "xxx", "added_at": "xxx"}
        """
        ...

    @abstractmethod
    def write_queue(self, queue: list) -> None:
        """
        写入 accounts_queue.json 队列

        Args:
            queue: 队列数组
        """
        ...

    def get_queue_length(self) -> int:
        """获取队列长度"""
        return len(self.read_queue())

    # ── accounts.json 操作 ────────────────────────────────

    @abstractmethod
    def read_accounts(self) -> list:
        """
        读取 accounts.json

        Returns:
            list: account 列表，如 ["561b705dc7e0-im-bot"]
        """
        ...

    @abstractmethod
    def write_accounts(self, accounts: list) -> None:
        """
        写入 accounts.json

        Args:
            accounts: account 列表
        """
        ...

    # ── 状态查询 ──────────────────────────────────────────

    @abstractmethod
    def query_status(self) -> dict:
        """
        查询当前 OpenClaw 微信接入状态

        Returns:
            dict: 包含 config 和 accounts 信息
        """
        ...

    # ── 登录 ──────────────────────────────────────────────

    @abstractmethod
    def login(self) -> Generator:
        """
        执行微信登录流程。

        这是一个生成器，逐步 yield SSE 事件：
        - qrcode 事件：包含二维码文本
        - progress 事件：登录进度

        Yields:
            str: SSE 格式的事件字符串
        """
        ...

    # ── Gateway 管理 ──────────────────────────────────────

    @abstractmethod
    def restart_gateway(self) -> None:
        """重启 openclaw-gateway 服务"""
        ...

    @abstractmethod
    def check_gateway(self) -> str:
        """
        检查 gateway 服务状态

        Returns:
            str: 服务状态，如 "active"
        """
        ...

    # ── 实例健康检查（远程模式用） ────────────────────────

    def check_instance_health(self) -> bool:
        """
        检查实例是否健康。

        本地模式默认返回 True。
        远程模式检查 Lighthouse 实例状态。

        Returns:
            bool: 实例是否健康
        """
        return True

    # ── 标识 ──────────────────────────────────────────────

    @abstractmethod
    def get_instance_id(self) -> str:
        """
        获取当前后端对应的实例标识

        Returns:
            str: 实例 ID（本地模式返回 "local"）
        """
        ...
