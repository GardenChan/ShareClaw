"""Flask 路由定义"""

from pathlib import Path

from flask import Blueprint, Response, send_file

bp = Blueprint("shareclaw", __name__)


@bp.route("/rotate", methods=["GET", "POST"])
def rotate():
    """坐席轮转接口 —— SSE 流式返回"""
    from shareclaw.claw.rotate import rotate_stream

    return Response(
        rotate_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲，确保流式传输
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        },
    )


@bp.route("/rotate", methods=["OPTIONS"])
def rotate_options():
    """CORS 预检请求"""
    return Response("", headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    })


@bp.route("/health", methods=["GET"])
def health():
    """健康检查接口"""
    return {"status": "ok"}


@bp.route("/logo.png", methods=["GET"])
def logo():
    """前端 Logo 图片"""
    logo_path = Path(__file__).resolve().parents[2] / "shareclaw.png"
    return send_file(logo_path, mimetype="image/png")


@bp.route("/", methods=["GET"])
def index_page():
    """前端测试页面"""
    from flask import render_template
    return render_template("index.html")