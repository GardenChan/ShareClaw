"""Web 服务模块"""


def create_app():
    """延迟导入以避免循环依赖"""
    from shareclaw.server.app import create_app as _create_app
    return _create_app()


__all__ = ["create_app"]
