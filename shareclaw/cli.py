"""ShareClaw CLI - 命令行入口"""

import argparse
import os
import sys


def main():
    """CLI 主入口"""
    parser = argparse.ArgumentParser(
        prog="shareclaw",
        description="ShareClaw - 云端 OpenClaw 微信坐席共享轮转管理服务",
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # serve 命令
    serve_parser = subparsers.add_parser("serve", help="启动 Web 服务")
    serve_parser.add_argument(
        "-p", "--port",
        type=int,
        default=int(os.environ.get("PORT", 9000)),
        help="监听端口（默认 9000，可通过 PORT 环境变量设置）",
    )
    serve_parser.add_argument(
        "-H", "--host",
        type=str,
        default="0.0.0.0",
        help="监听地址（默认 0.0.0.0）",
    )
    serve_parser.add_argument(
        "--debug",
        action="store_true",
        help="启用 Flask 调试模式",
    )

    # version 命令
    subparsers.add_parser("version", help="显示版本信息")

    args = parser.parse_args()

    if args.command == "serve":
        _cmd_serve(args)
    elif args.command == "version":
        _cmd_version()
    else:
        parser.print_help()
        sys.exit(1)


def _cmd_serve(args):
    """启动 Web 服务"""
    mode = os.environ.get("SHARECLAW_MODE", "local").strip().lower()

    if mode == "remote":
        # 远程模式需要腾讯云配置
        missing = []
        for var in ("TENCENT_SECRET_ID", "TENCENT_SECRET_KEY", "LIGHTHOUSE_INSTANCE_IDS"):
            if not os.environ.get(var):
                missing.append(var)

        if missing:
            print(f"❌ 远程模式缺少必要的环境变量：{', '.join(missing)}", file=sys.stderr)
            print("", file=sys.stderr)
            print("请通过以下任一方式设置：", file=sys.stderr)
            print("  方式一：创建 .env 文件（参考 .env.example）", file=sys.stderr)
            print("  方式二：直接 export 环境变量", file=sys.stderr)
            sys.exit(1)

    from shareclaw.server import create_app

    app = create_app()

    max_queue = os.environ.get("SHARECLAW_MAX_QUEUE_SIZE", "6")

    print(f"🚀 ShareClaw 服务启动中...")
    print(f"   部署模式: {mode}")
    print(f"   队列上限: {max_queue}")
    if mode == "remote":
        instance_ids = os.environ.get("LIGHTHOUSE_INSTANCE_IDS", "")
        count = len([i for i in instance_ids.split(",") if i.strip()])
        print(f"   实例数量: {count}")
    print(f"   监听地址: http://{args.host}:{args.port}")
    print(f"   测试页面: http://localhost:{args.port}")
    print(f"   健康检查: http://localhost:{args.port}/health")
    print(f"   坐席轮转: http://localhost:{args.port}/rotate")
    print()

    app.run(host=args.host, port=args.port, debug=args.debug)


def _cmd_version():
    """显示版本信息"""
    from shareclaw import __version__
    print(f"ShareClaw v{__version__}")


if __name__ == "__main__":
    main()
