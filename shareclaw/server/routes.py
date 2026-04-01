"""Flask 路由定义"""

import os
import hashlib
import hmac
import secrets
import time
from functools import wraps
from pathlib import Path

from flask import Blueprint, Response, send_file, request, jsonify

bp = Blueprint("shareclaw", __name__)

# 虾主 token 缓存（token -> 过期时间戳）
_admin_tokens: dict = {}
_ADMIN_TOKEN_TTL = 7 * 24 * 3600  # 7 天有效期


def _get_admin_password() -> str:
    """获取虾主管理密码"""
    return os.environ.get("SHARECLAW_ADMIN_PASSWORD", "").strip()


def _verify_admin_password(password: str) -> bool:
    """验证虾主密码"""
    expected = _get_admin_password()
    if not expected:
        return True  # 未设置密码时不拦截
    return hmac.compare_digest(password, expected)


def _create_admin_token() -> str:
    """生成虾主 token"""
    token = secrets.token_urlsafe(32)
    _admin_tokens[token] = time.time() + _ADMIN_TOKEN_TTL
    return token


def _check_admin_token() -> bool:
    """检查请求中是否带有有效的虾主 token"""
    if not _get_admin_password():
        return True  # 未设置密码时不拦截

    token = request.headers.get("X-Admin-Token", "") or request.args.get("admin_token", "")
    if not token:
        return False
    expire = _admin_tokens.get(token)
    if not expire or time.time() > expire:
        _admin_tokens.pop(token, None)
        return False
    return True


def _require_admin(f):
    """装饰器：要求虾主身份"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _check_admin_token():
            return jsonify({"error": "unauthorized", "message": "请先登录虾主管理面板"}), 401
        return f(*args, **kwargs)
    return decorated


def _get_sharing_store():
    """获取共享存储实例（懒加载）"""
    from shareclaw.sharing.store import SharingStore
    from shareclaw.config import get_config
    config = get_config()
    data_dir = config.get("shareclaw_home") or os.path.expanduser("~/.shareclaw")
    return SharingStore(data_dir)


def _get_user_manager():
    """获取用户管理器（懒加载）"""
    from shareclaw.sharing.user import UserManager
    store = _get_sharing_store()
    settings = store.read_settings()
    return UserManager(store, default_quota_hours=settings.get("default_quota_hours", 8))


def _get_invitation_manager():
    """获取邀请码管理器（懒加载）"""
    from shareclaw.sharing.invitation import InvitationManager
    return InvitationManager(_get_sharing_store())


# ── 虾主登录 ──────────────────────────────────────────────

@bp.route("/api/admin/login", methods=["POST"])
def admin_login():
    """虾主密码登录，返回 token"""
    data = request.get_json(silent=True) or {}
    password = data.get("password", "")

    if not _get_admin_password():
        # 未设置密码，直接通过
        return jsonify({"ok": True, "token": _create_admin_token(), "no_password": True})

    if _verify_admin_password(password):
        return jsonify({"ok": True, "token": _create_admin_token()})

    return jsonify({"ok": False, "message": "密码不对哦，问问虾主吧"}), 403


@bp.route("/api/admin/check", methods=["GET"])
def admin_check():
    """检查当前 token 是否有效"""
    has_password = bool(_get_admin_password())
    if not has_password:
        return jsonify({"ok": True, "has_password": False})
    return jsonify({"ok": _check_admin_token(), "has_password": True})


# ── 主页面 ────────────────────────────────────────────────

@bp.route("/", methods=["GET"])
def index_page():
    """前端轮转页面"""
    from flask import render_template
    return render_template("index.html")


@bp.route("/dashboard", methods=["GET"])
def dashboard_page():
    """Dashboard 管理页面"""
    from flask import render_template
    return render_template("dashboard.html")


# ── 坐席轮转 ──────────────────────────────────────────────

@bp.route("/rotate", methods=["GET", "POST"])
def rotate():
    """坐席轮转接口 —— SSE 流式返回，支持用户身份和邀请码"""
    from shareclaw.claw.rotate import rotate_stream

    # 从请求参数获取用户信息
    user_id = request.args.get("user_id", "").strip()
    user_name = request.args.get("user_name", "").strip()
    invite_code = request.args.get("invite", "").strip()

    # 验证邀请码（如果启用了邀请机制）
    store = _get_sharing_store()
    settings = store.read_settings()

    if settings.get("require_invite", False):
        if not invite_code:
            return Response(
                _error_sse("需要邀请码才能使用，请联系虾主获取"),
                mimetype="text/event-stream",
            )
        inv_mgr = _get_invitation_manager()
        valid, msg = inv_mgr.validate(invite_code)
        if not valid:
            return Response(
                _error_sse(msg),
                mimetype="text/event-stream",
            )

    # 用户身份处理
    user_mgr = _get_user_manager()
    if user_id:
        # 先注册（新用户）或获取（老用户），确保用户存在
        user_mgr.register(user_id, user_name or user_id, invite_code)

        # 使用邀请码
        if invite_code:
            inv_mgr = _get_invitation_manager()
            inv_mgr.use(invite_code, user_id)

        # 再检查配额
        has_quota, remaining = user_mgr.check_quota(user_id)
        if not has_quota:
            return Response(
                _error_sse("今日配额已用完，请明天再来"),
                mimetype="text/event-stream",
            )

    def stream_with_user_tracking():
        """包装 rotate_stream，在完成时记录用户 session"""
        from shareclaw.server.sse import sse_event
        import json

        for event_str in rotate_stream():
            yield event_str

            # 解析 SSE 事件，在 done 时记录 session
            if user_id and "event: done" in event_str:
                try:
                    data_line = [l for l in event_str.split("\n") if l.startswith("data: ")][0]
                    data = json.loads(data_line[6:])
                    account = data.get("queue", {}).get("accounts", [{}])[-1].get("account", "")
                    instance_id = data.get("instance_id", "local")
                    if account:
                        user_mgr.start_session(user_id, account, instance_id)
                except Exception:
                    pass

    return Response(
        stream_with_user_tracking(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
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


# ── Dashboard API ─────────────────────────────────────────

@bp.route("/api/status", methods=["GET"])
def api_status():
    """Dashboard 状态概览"""
    store = _get_sharing_store()
    user_mgr = _get_user_manager()
    settings = store.read_settings()

    active_users = user_mgr.get_active_users()
    all_users = user_mgr.get_all_users_summary()

    from shareclaw.config import get_config
    config = get_config()

    return jsonify({
        "mode": config["mode"],
        "max_queue_size": config["max_queue_size"],
        "active_users": active_users,
        "total_users": len(all_users),
        "online_count": len(active_users),
        "settings": settings,
    })


@bp.route("/api/users", methods=["GET"])
def api_users():
    """所有用户列表"""
    user_mgr = _get_user_manager()
    return jsonify(user_mgr.get_all_users_summary())


@bp.route("/api/history", methods=["GET"])
def api_history():
    """轮转历史记录"""
    store = _get_sharing_store()
    history = store.read_history()
    # 最新的在前
    return jsonify(list(reversed(history[-50:])))


@bp.route("/api/invitations", methods=["GET"])
def api_invitations():
    """邀请码列表"""
    inv_mgr = _get_invitation_manager()
    return jsonify(inv_mgr.list_all())


@bp.route("/api/invitations", methods=["POST"])
@_require_admin
def api_create_invitation():
    """创建邀请码"""
    data = request.get_json(silent=True) or {}
    inv_mgr = _get_invitation_manager()
    code = inv_mgr.create(
        created_by=data.get("created_by", "虾主"),
    )

    from shareclaw.config import get_config
    config = get_config()
    host = request.host

    return jsonify({
        "code": code,
        "invite_url": f"http://{host}/?invite={code}",
    })


@bp.route("/api/invitations/<code>", methods=["DELETE"])
@_require_admin
def api_delete_invitation(code):
    """删除邀请码"""
    inv_mgr = _get_invitation_manager()
    if inv_mgr.delete(code):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "message": "邀请码不存在"}), 404


@bp.route("/api/settings", methods=["GET"])
def api_get_settings():
    """获取虾主设置"""
    store = _get_sharing_store()
    return jsonify(store.read_settings())


@bp.route("/api/settings", methods=["PUT"])
@_require_admin
def api_update_settings():
    """更新虾主设置"""
    store = _get_sharing_store()
    data = request.get_json(silent=True) or {}
    settings = store.read_settings()
    settings.update(data)
    store.write_settings(settings)
    return jsonify(settings)


@bp.route("/api/cost-split", methods=["GET"])
def api_cost_split():
    """费用分摊信息"""
    store = _get_sharing_store()
    user_mgr = _get_user_manager()
    settings = store.read_settings()

    all_users = user_mgr.get_all_users_summary()
    total_users = len(all_users)
    monthly_cost = settings.get("monthly_cost", 0)

    return jsonify({
        "monthly_cost": monthly_cost,
        "total_users": total_users,
        "cost_per_user": round(monthly_cost / total_users, 2) if total_users > 0 else 0,
        "currency": "¥",
    })


# ── 模型配置 API ──────────────────────────────────────────

@bp.route("/api/models/configs", methods=["GET"])
@_require_admin
def api_list_model_configs():
    """获取虾主预配置的模型列表"""
    store = _get_sharing_store()
    return jsonify(store.read_model_configs())


@bp.route("/api/models/configs", methods=["POST"])
@_require_admin
def api_add_model_config():
    """添加模型配置"""
    data = request.get_json(silent=True) or {}
    required = ["name", "base_url", "api_key", "api_type", "model_id", "model_name"]
    for field in required:
        if not data.get(field, "").strip():
            return jsonify({"ok": False, "message": f"缺少必填项: {field}"}), 400

    store = _get_sharing_store()
    config = store.add_model_config({
        "name": data["name"].strip(),
        "base_url": data["base_url"].strip(),
        "api_key": data["api_key"].strip(),
        "api_type": data["api_type"].strip(),
        "model_id": data["model_id"].strip(),
        "model_name": data["model_name"].strip(),
    })
    return jsonify({"ok": True, "data": config})


@bp.route("/api/models/configs/<int:config_id>", methods=["DELETE"])
@_require_admin
def api_delete_model_config(config_id):
    """删除模型配置"""
    store = _get_sharing_store()
    if store.delete_model_config(config_id):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "message": "配置不存在"}), 404


@bp.route("/api/models/status", methods=["GET"])
@_require_admin
def api_model_status():
    """获取远程实例上的当前模型配置状态"""
    from shareclaw.config import get_config
    config = get_config()
    mode = config["mode"]

    if mode == "local":
        return _read_local_model_status(config)
    else:
        return _read_remote_model_status(config)


@bp.route("/api/models/apply", methods=["POST"])
@_require_admin
def api_apply_model():
    """添加并应用模型到 OpenClaw 实例"""
    data = request.get_json(silent=True) or {}
    config_id = data.get("config_id")
    if not config_id:
        return jsonify({"ok": False, "message": "缺少 config_id"}), 400

    store = _get_sharing_store()
    model_config = store.get_model_config(config_id)
    if not model_config:
        return jsonify({"ok": False, "message": "模型配置不存在"}), 404

    from shareclaw.config import get_config
    config = get_config()
    mode = config["mode"]
    provider_name = model_config["name"].lower().replace(" ", "-") + "-provider"

    try:
        if mode == "local":
            result = _apply_model_local(config, provider_name, model_config)
        else:
            result = _apply_model_remote(config, provider_name, model_config)
        return jsonify({"ok": True, "message": f"模型 {model_config['model_name']} 配置成功", "data": result})
    except Exception as e:
        return jsonify({"ok": False, "message": f"配置失败: {str(e)}"}), 500


@bp.route("/api/models/switch", methods=["POST"])
@_require_admin
def api_switch_model():
    """切换应用中的模型"""
    data = request.get_json(silent=True) or {}
    provider_name = data.get("provider_name", "").strip()
    model_id = data.get("model_id", "").strip()
    if not provider_name or not model_id:
        return jsonify({"ok": False, "message": "缺少 provider_name 或 model_id"}), 400

    from shareclaw.config import get_config
    config = get_config()
    mode = config["mode"]

    try:
        if mode == "local":
            result = _switch_model_local(config, provider_name, model_id)
        else:
            result = _switch_model_remote(config, provider_name, model_id)
        return jsonify({"ok": True, "message": f"已切换到 {provider_name}/{model_id}", "data": result})
    except Exception as e:
        return jsonify({"ok": False, "message": f"切换失败: {str(e)}"}), 500


@bp.route("/api/models/remove-provider", methods=["POST"])
@_require_admin
def api_remove_provider():
    """从 OpenClaw 实例上删除一个 provider"""
    data = request.get_json(silent=True) or {}
    provider_name = data.get("provider_name", "").strip()
    if not provider_name:
        return jsonify({"ok": False, "message": "缺少 provider_name"}), 400

    from shareclaw.config import get_config
    config = get_config()
    mode = config["mode"]

    try:
        if mode == "local":
            result = _remove_provider_local(config, provider_name)
        else:
            result = _remove_provider_remote(config, provider_name)
        return jsonify({"ok": True, "message": f"已删除 {provider_name}", "data": result})
    except Exception as e:
        return jsonify({"ok": False, "message": f"删除失败: {str(e)}"}), 500


# ── 模型配置辅助函数 ──────────────────────────────────────

def _read_local_model_status(config):
    """本地模式读取模型状态"""
    import json
    oc_path = os.path.join(config["openclaw_home"], "openclaw.json")
    if not os.path.exists(oc_path):
        return jsonify({"configured": False, "providers": [], "primary": None})
    try:
        with open(oc_path, "r", encoding="utf-8") as f:
            oc = json.load(f)
        providers_dict = oc.get("models", {}).get("providers", {})
        primary = oc.get("agents", {}).get("defaults", {}).get("model", {}).get("primary", "")
        active_pname = primary.split("/")[0] if "/" in primary else ""
        providers = []
        for pname, pconf in providers_dict.items():
            models_list = pconf.get("models", [])
            first = models_list[0] if models_list else {}
            providers.append({
                "provider_name": pname,
                "model_id": first.get("id", ""),
                "model_name": first.get("name", ""),
                "api_type": pconf.get("api", ""),
                "is_active": pname == active_pname,
            })
        return jsonify({"configured": bool(providers_dict), "providers": providers, "primary": primary})
    except Exception:
        return jsonify({"configured": False, "providers": [], "primary": None})


def _read_remote_model_status(config):
    """远程模式读取模型状态（第一个实例）"""
    import json as _json
    from shareclaw.claw.commands import CMD_READ_MODEL_CONFIG
    from shareclaw.cloud.client import create_credential, create_tat_client
    from shareclaw.cloud.tat import run_command_and_wait

    cred = create_credential(config)
    tat = create_tat_client(cred, config)
    instance_id = config["instance_ids"][0]

    try:
        result = run_command_and_wait(tat, instance_id, CMD_READ_MODEL_CONFIG, timeout=15)
        if result["task_status"] != "SUCCESS":
            return jsonify({"configured": False, "providers": [], "primary": None})

        output = result["output"].strip()
        data = _json.loads(output)
        providers_dict = data.get("providers") or {}
        primary = data.get("primary") or ""
        active_pname = primary.split("/")[0] if "/" in primary else ""

        providers = []
        for pname, pconf in providers_dict.items():
            models_list = pconf.get("models", [])
            first = models_list[0] if models_list else {}
            providers.append({
                "provider_name": pname,
                "model_id": first.get("id", ""),
                "model_name": first.get("name", ""),
                "api_type": pconf.get("api", ""),
                "is_active": pname == active_pname,
            })
        return jsonify({"configured": bool(providers_dict), "providers": providers, "primary": primary})
    except Exception:
        return jsonify({"configured": False, "providers": [], "primary": None})


def _apply_model_local(config, provider_name, model_config):
    """本地模式：修改 openclaw.json 添加模型并设为 primary"""
    import json as _json
    oc_path = os.path.join(config["openclaw_home"], "openclaw.json")
    with open(oc_path, "r", encoding="utf-8") as f:
        oc = _json.load(f)

    if "models" not in oc:
        oc["models"] = {}
    oc["models"]["mode"] = "merge"
    if "providers" not in oc["models"]:
        oc["models"]["providers"] = {}

    oc["models"]["providers"][provider_name] = {
        "baseUrl": model_config["base_url"],
        "apiKey": model_config["api_key"],
        "api": model_config["api_type"],
        "models": [{"id": model_config["model_id"], "name": model_config["model_name"]}],
    }

    if "agents" not in oc:
        oc["agents"] = {}
    if "defaults" not in oc["agents"]:
        oc["agents"]["defaults"] = {}
    if "model" not in oc["agents"]["defaults"]:
        oc["agents"]["defaults"]["model"] = {}
    oc["agents"]["defaults"]["model"]["primary"] = f"{provider_name}/{model_config['model_id']}"

    with open(oc_path, "w", encoding="utf-8") as f:
        _json.dump(oc, f, ensure_ascii=False, indent=2)

    import subprocess
    subprocess.run(["systemctl", "--user", "restart", "openclaw-gateway"], capture_output=True, timeout=30)
    return {"provider_name": provider_name, "model_name": model_config["model_name"]}


def _apply_model_remote(config, provider_name, model_config):
    """远程模式：通过 TAT 修改 openclaw.json"""
    from shareclaw.claw.commands import cmd_add_provider, cmd_set_merge_mode, cmd_set_primary_model, CMD_RESTART_GATEWAY
    from shareclaw.cloud.client import create_credential, create_tat_client
    from shareclaw.cloud.tat import run_command_and_wait

    cred = create_credential(config)
    tat = create_tat_client(cred, config)
    instance_id = config["instance_ids"][0]

    # 1. 添加 provider
    cmd1 = cmd_add_provider(provider_name, model_config["base_url"], model_config["api_key"],
                            model_config["api_type"], model_config["model_id"], model_config["model_name"])
    run_command_and_wait(tat, instance_id, cmd1, timeout=30)

    # 2. 设置 merge mode
    run_command_and_wait(tat, instance_id, cmd_set_merge_mode(), timeout=15)

    # 3. 设置 primary
    cmd3 = cmd_set_primary_model(provider_name, model_config["model_id"])
    run_command_and_wait(tat, instance_id, cmd3, timeout=15)

    # 4. 重启 gateway
    run_command_and_wait(tat, instance_id, CMD_RESTART_GATEWAY, timeout=30)

    return {"provider_name": provider_name, "model_name": model_config["model_name"]}


def _switch_model_local(config, provider_name, model_id):
    """本地模式切换主模型"""
    import json as _json
    oc_path = os.path.join(config["openclaw_home"], "openclaw.json")
    with open(oc_path, "r", encoding="utf-8") as f:
        oc = _json.load(f)
    oc["agents"]["defaults"]["model"]["primary"] = f"{provider_name}/{model_id}"
    with open(oc_path, "w", encoding="utf-8") as f:
        _json.dump(oc, f, ensure_ascii=False, indent=2)

    import subprocess
    subprocess.run(["systemctl", "--user", "restart", "openclaw-gateway"], capture_output=True, timeout=30)
    return {"new_primary": f"{provider_name}/{model_id}"}


def _switch_model_remote(config, provider_name, model_id):
    """远程模式切换主模型"""
    from shareclaw.claw.commands import cmd_set_primary_model, CMD_RESTART_GATEWAY
    from shareclaw.cloud.client import create_credential, create_tat_client
    from shareclaw.cloud.tat import run_command_and_wait

    cred = create_credential(config)
    tat = create_tat_client(cred, config)
    instance_id = config["instance_ids"][0]

    run_command_and_wait(tat, instance_id, cmd_set_primary_model(provider_name, model_id), timeout=15)
    run_command_and_wait(tat, instance_id, CMD_RESTART_GATEWAY, timeout=30)
    return {"new_primary": f"{provider_name}/{model_id}"}


def _remove_provider_local(config, provider_name):
    """本地模式删除 provider"""
    import json as _json
    oc_path = os.path.join(config["openclaw_home"], "openclaw.json")
    with open(oc_path, "r", encoding="utf-8") as f:
        oc = _json.load(f)
    providers = oc.get("models", {}).get("providers", {})
    if provider_name in providers:
        del providers[provider_name]
    with open(oc_path, "w", encoding="utf-8") as f:
        _json.dump(oc, f, ensure_ascii=False, indent=2)

    import subprocess
    subprocess.run(["systemctl", "--user", "restart", "openclaw-gateway"], capture_output=True, timeout=30)
    return {"deleted": provider_name}


def _remove_provider_remote(config, provider_name):
    """远程模式删除 provider"""
    from shareclaw.claw.commands import cmd_delete_provider, CMD_RESTART_GATEWAY
    from shareclaw.cloud.client import create_credential, create_tat_client
    from shareclaw.cloud.tat import run_command_and_wait

    cred = create_credential(config)
    tat = create_tat_client(cred, config)
    instance_id = config["instance_ids"][0]

    run_command_and_wait(tat, instance_id, cmd_delete_provider(provider_name), timeout=15)
    run_command_and_wait(tat, instance_id, CMD_RESTART_GATEWAY, timeout=30)
    return {"deleted": provider_name}


# ── 静态资源 ──────────────────────────────────────────────

@bp.route("/health", methods=["GET"])
def health():
    """健康检查接口"""
    return {"status": "ok"}


@bp.route("/logo.png", methods=["GET"])
def logo():
    """前端 Logo 图片"""
    logo_path = Path(__file__).resolve().parent / "shareclaw.png"
    return send_file(logo_path, mimetype="image/png")


# ── 工具函数 ──────────────────────────────────────────────

def _error_sse(message: str) -> str:
    """生成一条 error SSE 事件"""
    from shareclaw.server.sse import sse_event
    return sse_event("error", {"stage": "error", "message": message})
