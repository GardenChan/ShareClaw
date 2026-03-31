"""Flask 应用工厂"""

from flask import Flask

from shareclaw.server.routes import bp


def create_app():
    """
    创建并配置 Flask 应用

    Returns:
        Flask: 配置好的 Flask 应用实例
    """
    app = Flask(__name__, template_folder="templates")
    app.register_blueprint(bp)
    return app
