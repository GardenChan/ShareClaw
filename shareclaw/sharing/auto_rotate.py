"""
自动轮转定时器

定期检查在线用户的使用时长，超过配额则自动踢出。
使用简单的后台线程实现，无需引入 APScheduler 等外部依赖。
"""

import logging
import threading
import time
from datetime import datetime

logger = logging.getLogger(__name__)

# 全局自动轮转器实例
_auto_rotator = None


class AutoRotator:
    """
    自动轮转器。

    每 60 秒检查一次在线用户的使用时长，
    超过每日配额的用户会被自动踢出（从队列和 accounts.json 中移除）。
    """

    def __init__(self, store, user_manager, config, check_interval: int = 60):
        self.store = store
        self.user_manager = user_manager
        self.config = config
        self.check_interval = check_interval
        self._thread = None
        self._stop_event = threading.Event()

    def start(self):
        """启动自动轮转后台线程"""
        if self._thread and self._thread.is_alive():
            logger.info("自动轮转器已在运行")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="auto-rotator")
        self._thread.start()
        logger.info("自动轮转器已启动 (检查间隔: %ds)", self.check_interval)

    def stop(self):
        """停止自动轮转"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("自动轮转器已停止")

    def _run(self):
        """后台循环检查"""
        while not self._stop_event.is_set():
            try:
                self._check_and_evict()
            except Exception as e:
                logger.error(f"自动轮转检查出错: {e}")
            self._stop_event.wait(self.check_interval)

    def _check_and_evict(self):
        """检查所有在线用户，超额的自动踢出"""
        settings = self.store.read_settings()
        if not settings.get("auto_evict_enabled", False):
            return

        max_hours = settings.get("auto_evict_after_hours", 8)
        active_users = self.user_manager.get_active_users()

        for user_info in active_users:
            total_today = user_info["today_used_seconds"]
            quota_seconds = user_info["quota_hours"] * 3600

            if total_today >= quota_seconds:
                user_id = user_info["user_id"]
                account = user_info["account"]
                instance_id = user_info["instance_id"]

                logger.info(
                    f"用户 {user_id} 今日使用已达 {total_today}s (配额: {quota_seconds}s)，自动踢出"
                )

                # 结束用户 session
                self.user_manager.end_session(user_id, reason="quota_exceeded")

                # 从 accounts 和队列中移除
                self._evict_account(account, instance_id)

    def _evict_account(self, account: str, instance_id: str):
        """从 OpenClaw 中踢出指定 account"""
        try:
            from shareclaw.claw.backend import create_backend
            from shareclaw.claw.backend.remote import RemoteBackend

            if self.config.get("mode") == "local":
                backend = create_backend(self.config)
            else:
                backend = RemoteBackend(self.config, instance_id=instance_id)

            # 从 accounts.json 移除
            accounts = backend.read_accounts()
            if account in accounts:
                accounts.remove(account)
                backend.write_accounts(accounts)

            # 从队列移除
            queue = backend.read_queue()
            queue = [item for item in queue if item.get("account") != account]
            backend.write_queue(queue)

            # 重启 gateway
            backend.restart_gateway()

            logger.info(f"已自动踢出 account {account} 并重启 gateway")

        except Exception as e:
            logger.error(f"自动踢出 account {account} 失败: {e}")


def get_auto_rotator(store, user_manager, config) -> AutoRotator:
    """获取或创建全局自动轮转器"""
    global _auto_rotator
    if _auto_rotator is None:
        _auto_rotator = AutoRotator(store, user_manager, config)
    return _auto_rotator
