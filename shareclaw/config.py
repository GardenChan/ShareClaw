"""配置管理模块"""

import os


def get_config():
    """
    从环境变量读取配置，支持 local 和 remote 两种部署模式。

    环境变量：
      通用：
        - SHARECLAW_MODE: 部署模式，local 或 remote（默认 local）
        - SHARECLAW_MAX_QUEUE_SIZE: 队列最大长度（默认 6）

      本地模式 (local)：
        - OPENCLAW_HOME: OpenClaw 主目录（默认 ~/.openclaw）
        - SHARECLAW_HOME: ShareClaw 数据目录（默认 ~/.shareclaw）

      远程模式 (remote)：
        - TENCENT_SECRET_ID: 腾讯云 SecretId
        - TENCENT_SECRET_KEY: 腾讯云 SecretKey
        - LIGHTHOUSE_INSTANCE_IDS: Lighthouse 实例 ID（多个用逗号分隔）
        - LIGHTHOUSE_REGION: Lighthouse 地域（默认 ap-guangzhou）

    Returns:
        dict: 配置字典

    Raises:
        ValueError: 缺少必要的环境变量
    """
    mode = os.environ.get("SHARECLAW_MODE", "local").strip().lower()

    if mode not in ("local", "remote"):
        raise ValueError(f"不支持的部署模式: {mode}，请设置 SHARECLAW_MODE 为 local 或 remote")

    max_queue_size = int(os.environ.get("SHARECLAW_MAX_QUEUE_SIZE", "6"))

    config = {
        "mode": mode,
        "max_queue_size": max_queue_size,
    }

    if mode == "local":
        config.update(_load_local_config())
    else:
        config.update(_load_remote_config())

    return config


def _load_local_config():
    """加载本地模式配置"""
    home = os.path.expanduser("~")
    openclaw_home = os.path.expanduser(
        os.environ.get("OPENCLAW_HOME", os.path.join(home, ".openclaw"))
    )
    shareclaw_home = os.path.expanduser(
        os.environ.get("SHARECLAW_HOME", os.path.join(home, ".shareclaw"))
    )

    return {
        "openclaw_home": openclaw_home,
        "shareclaw_home": shareclaw_home,
    }


def _load_remote_config():
    """加载远程模式配置"""
    secret_id = os.environ.get("TENCENT_SECRET_ID", "")
    secret_key = os.environ.get("TENCENT_SECRET_KEY", "")
    instance_ids_raw = os.environ.get("LIGHTHOUSE_INSTANCE_IDS", "")
    region = os.environ.get("LIGHTHOUSE_REGION", "ap-guangzhou")

    if not secret_id or not secret_key:
        raise ValueError("远程模式缺少环境变量 TENCENT_SECRET_ID 或 TENCENT_SECRET_KEY")
    if not instance_ids_raw:
        raise ValueError("远程模式缺少环境变量 LIGHTHOUSE_INSTANCE_IDS")

    # 支持逗号分隔的多实例 ID
    instance_ids = [iid.strip() for iid in instance_ids_raw.split(",") if iid.strip()]
    if not instance_ids:
        raise ValueError("LIGHTHOUSE_INSTANCE_IDS 不能为空")

    return {
        "secret_id": secret_id,
        "secret_key": secret_key,
        "instance_ids": instance_ids,
        "region": region,
    }
