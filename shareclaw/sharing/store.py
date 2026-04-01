"""
JSON 文件存储层

管理 ~/.shareclaw/ 下的共享相关数据文件：
- users.json: 用户身份与配额
- invitations.json: 邀请码
- history.json: 轮转历史记录
- settings.json: 虾主配置（费用、配额默认值等）
"""

import json
import logging
import os
import threading
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class SharingStore:
    """
    基于 JSON 文件的持久化存储。

    所有读写操作通过文件锁保证线程安全。
    """

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, filename: str) -> str:
        return os.path.join(self.data_dir, filename)

    def _read(self, filename: str, default: Any = None):
        """线程安全地读取 JSON 文件"""
        path = self._path(filename)
        if not os.path.exists(path):
            return default if default is not None else {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            logger.warning(f"读取 {filename} 失败，返回默认值")
            return default if default is not None else {}

    def _write(self, filename: str, data: Any) -> None:
        """线程安全地写入 JSON 文件"""
        path = self._path(filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ── 用户 ──────────────────────────────────────────────

    def read_users(self) -> dict:
        with self._lock:
            return self._read("users.json", {})

    def write_users(self, users: dict) -> None:
        with self._lock:
            self._write("users.json", users)

    def get_user(self, user_id: str) -> dict | None:
        users = self.read_users()
        return users.get(user_id)

    def save_user(self, user_id: str, user_data: dict) -> None:
        with self._lock:
            users = self._read("users.json", {})
            users[user_id] = user_data
            self._write("users.json", users)

    # ── 邀请码 ────────────────────────────────────────────

    def read_invitations(self) -> dict:
        with self._lock:
            return self._read("invitations.json", {})

    def write_invitations(self, invitations: dict) -> None:
        with self._lock:
            self._write("invitations.json", invitations)

    def get_invitation(self, code: str) -> dict | None:
        invitations = self.read_invitations()
        return invitations.get(code)

    def save_invitation(self, code: str, data: dict) -> None:
        with self._lock:
            invitations = self._read("invitations.json", {})
            invitations[code] = data
            self._write("invitations.json", invitations)

    # ── 历史记录 ──────────────────────────────────────────

    def read_history(self) -> list:
        with self._lock:
            return self._read("history.json", [])

    def append_history(self, record: dict) -> None:
        with self._lock:
            history = self._read("history.json", [])
            history.append(record)
            # 只保留最近 500 条
            if len(history) > 500:
                history = history[-500:]
            self._write("history.json", history)

    def update_latest_history(self, user_id: str, updates: dict) -> None:
        """更新指定用户最近一条未结束的历史记录"""
        with self._lock:
            history = self._read("history.json", [])
            for record in reversed(history):
                if record.get("user") == user_id and record.get("ended_at") is None:
                    record.update(updates)
                    break
            self._write("history.json", history)

    # ── 虾主设置 ──────────────────────────────────────────

    def read_settings(self) -> dict:
        with self._lock:
            return self._read("settings.json", {
                "monthly_cost": 0,
                "require_invite": False,
                "default_quota_hours": 8,
                "auto_evict_enabled": False,
                "auto_evict_after_hours": 8,
            })

    def write_settings(self, settings: dict) -> None:
        with self._lock:
            self._write("settings.json", settings)

    # ── 模型配置 ──────────────────────────────────────────

    def read_model_configs(self) -> list:
        """读取虾主预配置的模型列表"""
        with self._lock:
            return self._read("model_configs.json", [])

    def write_model_configs(self, configs: list) -> None:
        with self._lock:
            self._write("model_configs.json", configs)

    def add_model_config(self, config: dict) -> dict:
        """添加一个模型配置，返回带 id 的配置"""
        with self._lock:
            configs = self._read("model_configs.json", [])
            # 生成自增 id
            max_id = max((c.get("id", 0) for c in configs), default=0)
            config["id"] = max_id + 1
            configs.append(config)
            self._write("model_configs.json", configs)
            return config

    def get_model_config(self, config_id: int) -> dict | None:
        configs = self.read_model_configs()
        for c in configs:
            if c.get("id") == config_id:
                return c
        return None

    def delete_model_config(self, config_id: int) -> bool:
        with self._lock:
            configs = self._read("model_configs.json", [])
            new_configs = [c for c in configs if c.get("id") != config_id]
            if len(new_configs) == len(configs):
                return False
            self._write("model_configs.json", new_configs)
            return True
