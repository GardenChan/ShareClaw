"""后端实现 —— 根据部署模式选择本地或远程后端"""

from shareclaw.claw.backend.base import ClawBackend
from shareclaw.claw.backend.local import LocalBackend
from shareclaw.claw.backend.remote import RemoteBackend


def create_backend(config) -> ClawBackend:
    """
    根据配置创建对应的后端实例

    Args:
        config: 配置字典（来自 get_config()）

    Returns:
        ClawBackend: 后端实例
    """
    mode = config["mode"]

    if mode == "local":
        return LocalBackend(config)
    elif mode == "remote":
        return RemoteBackend(config)
    else:
        raise ValueError(f"不支持的部署模式: {mode}")


__all__ = ["ClawBackend", "LocalBackend", "RemoteBackend", "create_backend"]
