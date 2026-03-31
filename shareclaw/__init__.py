"""
ShareClaw - 云端 OpenClaw 微信坐席共享轮转管理服务

让多人共享同一个云端 OpenClaw AI 助手的微信坐席。
基于 OpenClaw + openclaw-weixin 生态，支持本地与远程两种部署模式。
"""

__version__ = "0.1.0"
__author__ = "garden"


def rotate_stream():
    """延迟导入以避免循环依赖"""
    from shareclaw.claw.rotate import rotate_stream as _rotate_stream
    return _rotate_stream()


__all__ = ["rotate_stream", "__version__"]