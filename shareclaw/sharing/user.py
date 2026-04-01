"""
用户身份与配额管理模块

支持：
- 用户注册（通过邀请码）
- 每日使用时长配额
- 配额检查与消耗
- 在线坐席追踪（谁在用、用了多久）
"""

import logging
from datetime import datetime
from typing import Optional

from shareclaw.sharing.store import SharingStore

logger = logging.getLogger(__name__)


class UserManager:
    """用户管理器"""

    def __init__(self, store: SharingStore, default_quota_hours: int = 8):
        self.store = store
        self.default_quota_hours = default_quota_hours

    def register(self, user_id: str, name: str, invite_code: str = "") -> dict:
        """
        注册新用户

        Args:
            user_id: 用户唯一标识（前端生成或用户输入）
            name: 显示名称
            invite_code: 使用的邀请码

        Returns:
            dict: 用户数据
        """
        existing = self.store.get_user(user_id)
        if existing:
            logger.info(f"用户 {user_id} 已存在，返回现有数据")
            return existing

        user_data = {
            "name": name,
            "invite_code": invite_code,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "quota_hours_per_day": self.default_quota_hours,
            "today_used_seconds": 0,
            "last_reset_date": datetime.now().strftime("%Y-%m-%d"),
            "total_rotations": 0,
            "current_account": None,
            "current_instance": None,
            "session_started_at": None,
        }

        self.store.save_user(user_id, user_data)
        logger.info(f"新用户注册: {user_id} ({name})")
        return user_data

    def get_or_none(self, user_id: str) -> Optional[dict]:
        """获取用户，不存在返回 None"""
        return self.store.get_user(user_id)

    def check_quota(self, user_id: str) -> tuple[bool, int]:
        """
        检查用户今日是否还有配额

        Returns:
            (has_quota, remaining_seconds)
        """
        user = self.store.get_user(user_id)
        if not user:
            return False, 0

        # 每日重置
        today = datetime.now().strftime("%Y-%m-%d")
        if user.get("last_reset_date") != today:
            user["today_used_seconds"] = 0
            user["last_reset_date"] = today
            self.store.save_user(user_id, user)

        quota_seconds = user.get("quota_hours_per_day", self.default_quota_hours) * 3600
        used = user.get("today_used_seconds", 0)
        remaining = max(0, quota_seconds - used)

        return remaining > 0, remaining

    def start_session(self, user_id: str, account: str, instance_id: str) -> None:
        """记录用户开始使用坐席"""
        user = self.store.get_user(user_id)
        if not user:
            return

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user["current_account"] = account
        user["current_instance"] = instance_id
        user["session_started_at"] = now
        user["total_rotations"] = user.get("total_rotations", 0) + 1
        self.store.save_user(user_id, user)

        # 写入历史
        self.store.append_history({
            "user": user_id,
            "name": user.get("name", user_id),
            "account": account,
            "instance_id": instance_id,
            "started_at": now,
            "ended_at": None,
            "ended_reason": None,
        })

        logger.info(f"用户 {user_id} 开始使用坐席 {account} (实例: {instance_id})")

    def end_session(self, user_id: str, reason: str = "manual") -> None:
        """结束用户的坐席使用，累计使用时长"""
        user = self.store.get_user(user_id)
        if not user or not user.get("session_started_at"):
            return

        now = datetime.now()
        started = datetime.strptime(user["session_started_at"], "%Y-%m-%d %H:%M:%S")
        duration_seconds = int((now - started).total_seconds())

        # 累计今日使用时长
        user["today_used_seconds"] = user.get("today_used_seconds", 0) + duration_seconds
        user["current_account"] = None
        user["current_instance"] = None
        user["session_started_at"] = None
        self.store.save_user(user_id, user)

        # 更新历史
        self.store.update_latest_history(user_id, {
            "ended_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "ended_reason": reason,
        })

        logger.info(f"用户 {user_id} 结束使用 (原因: {reason}, 时长: {duration_seconds}秒)")

    def get_active_users(self) -> list:
        """获取当前在线的用户列表"""
        users = self.store.read_users()
        active = []
        now = datetime.now()

        for user_id, data in users.items():
            if data.get("session_started_at"):
                started = datetime.strptime(data["session_started_at"], "%Y-%m-%d %H:%M:%S")
                duration = int((now - started).total_seconds())
                active.append({
                    "user_id": user_id,
                    "name": data.get("name", user_id),
                    "account": data.get("current_account"),
                    "instance_id": data.get("current_instance"),
                    "started_at": data["session_started_at"],
                    "duration_seconds": duration,
                    "quota_hours": data.get("quota_hours_per_day", 8),
                    "today_used_seconds": data.get("today_used_seconds", 0) + duration,
                })

        return active

    def get_all_users_summary(self) -> list:
        """获取所有用户概要"""
        users = self.store.read_users()
        summary = []
        for user_id, data in users.items():
            summary.append({
                "user_id": user_id,
                "name": data.get("name", user_id),
                "created_at": data.get("created_at"),
                "total_rotations": data.get("total_rotations", 0),
                "is_online": data.get("session_started_at") is not None,
                "current_account": data.get("current_account"),
                "quota_hours": data.get("quota_hours_per_day", 8),
                "today_used_seconds": data.get("today_used_seconds", 0),
            })
        return summary
