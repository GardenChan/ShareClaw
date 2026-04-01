"""Flask 应用工厂"""

import logging
import os

from flask import Flask

from shareclaw.server.routes import bp

logger = logging.getLogger(__name__)


def create_app():
    """
    创建并配置 Flask 应用

    Returns:
        Flask: 配置好的 Flask 应用实例
    """
    app = Flask(__name__, template_folder="templates")
    app.register_blueprint(bp)

    # 启动自动轮转器（如果配置了）
    _start_auto_rotator()

    return app


def _start_auto_rotator():
    """尝试启动自动轮转后台线程"""
    try:
        from shareclaw.config import get_config
        from shareclaw.sharing.store import SharingStore
        from shareclaw.sharing.user import UserManager
        from shareclaw.sharing.auto_rotate import get_auto_rotator

        config = get_config()
        data_dir = config.get("shareclaw_home") or os.path.expanduser("~/.shareclaw")
        store = SharingStore(data_dir)
        settings = store.read_settings()

        if settings.get("auto_evict_enabled", False):
            user_mgr = UserManager(store, default_quota_hours=settings.get("default_quota_hours", 8))
            rotator = get_auto_rotator(store, user_mgr, config)
            rotator.start()
            logger.info("自动轮转器已启动")
        else:
            logger.info("自动轮转未启用（可在 Dashboard 设置中开启）")
    except Exception as e:
        logger.warning(f"自动轮转器启动失败（不影响基本功能）: {e}")
