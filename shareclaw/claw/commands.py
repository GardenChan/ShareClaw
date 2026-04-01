"""OpenClaw 业务命令定义（远程模式 TAT 使用）"""

import base64

# ── 目录初始化 ────────────────────────────────────────────

CMD_ENSURE_SHARECLAW_DIR = "mkdir -p ~/.shareclaw"

# ── 状态查询 ──────────────────────────────────────────────

# 查询当前接入的微信
# 注意：用子 shell 隔离 || 的作用域，避免 jq 失败时跳过 SEPARATOR
CMD_QUERY_STATUS = (
    "jq '{models,channels,gateway,agents:{defaults:.agents.defaults}}' ~/.openclaw/openclaw.json && "
    "echo '---ACCOUNTS_SEPARATOR---' && "
    "(cat ~/.openclaw/openclaw-weixin/accounts.json 2>/dev/null || echo '[]')"
)

# ── 队列文件操作 ──────────────────────────────────────────

def cmd_read_queue() -> str:
    """读取 accounts_queue.json"""
    return "cat ~/.shareclaw/accounts_queue.json 2>/dev/null || echo '[]'"


def cmd_write_queue(queue_json: str) -> str:
    """写入 accounts_queue.json（使用 base64 编码传输，避免 shell 注入）"""
    encoded = base64.b64encode(queue_json.encode("utf-8")).decode("utf-8")
    return f"echo '{encoded}' | base64 -d > ~/.shareclaw/accounts_queue.json"


# ── accounts.json 操作 ────────────────────────────────────

def cmd_read_accounts() -> str:
    """读取 accounts.json"""
    return "cat ~/.openclaw/openclaw-weixin/accounts.json 2>/dev/null || echo '[]'"


def cmd_write_accounts(accounts_json: str) -> str:
    """写入 accounts.json（使用 base64 编码传输，避免 shell 注入）"""
    encoded = base64.b64encode(accounts_json.encode("utf-8")).decode("utf-8")
    return f"echo '{encoded}' | base64 -d > ~/.openclaw/openclaw-weixin/accounts.json"


# ── 登录 ──────────────────────────────────────────────────

# 登录新微信（会输出二维码并阻塞等待扫码回调）
CMD_LOGIN = (
    "openclaw channels login --channel openclaw-weixin 2>&1 | "
    "stdbuf -oL sed -n '/使用微信扫描以下二维码/,$p'"
)

# ── Gateway 管理 ──────────────────────────────────────────

# 重启 gateway
CMD_RESTART_GATEWAY = "systemctl --user restart openclaw-gateway"

# 检查 gateway 状态
CMD_CHECK_GATEWAY = "systemctl --user is-active openclaw-gateway"


# ── 模型配置 ──────────────────────────────────────────────

# 读取当前已配置的 providers 和 primary model
CMD_READ_MODEL_CONFIG = (
    "jq '{providers: .models.providers, primary: .agents.defaults.model.primary}' "
    "~/.openclaw/openclaw.json 2>/dev/null || echo '{}'"
)


def cmd_add_provider(provider_name: str, base_url: str, api_key: str, api_type: str, model_id: str, model_name: str) -> str:
    """构建 jq 命令：添加模型供应商到 openclaw.json（使用 base64 安全传参）"""
    import json as _json
    provider_config = _json.dumps({
        "baseUrl": base_url,
        "apiKey": api_key,
        "api": api_type,
        "models": [{"id": model_id, "name": model_name}],
    }, ensure_ascii=False)
    encoded = base64.b64encode(provider_config.encode("utf-8")).decode("utf-8")
    return (
        f"PROV=$(echo '{encoded}' | base64 -d) && "
        f"jq --arg pname '{provider_name}' --argjson pconf \"$PROV\" "
        f"'.models.providers[$pname] = $pconf' "
        f"~/.openclaw/openclaw.json > /tmp/_oc_tmp.json && "
        f"mv /tmp/_oc_tmp.json ~/.openclaw/openclaw.json"
    )


def cmd_set_merge_mode() -> str:
    """构建 jq 命令：设置 models.mode = merge"""
    return (
        "jq '.models.mode = \"merge\"' ~/.openclaw/openclaw.json "
        "> /tmp/_oc_tmp.json && mv /tmp/_oc_tmp.json ~/.openclaw/openclaw.json"
    )


def cmd_set_primary_model(provider_name: str, model_id: str) -> str:
    """构建 jq 命令：设置主模型"""
    return (
        f"jq '.agents.defaults.model.primary = \"{provider_name}/{model_id}\"' "
        f"~/.openclaw/openclaw.json > /tmp/_oc_tmp.json && "
        f"mv /tmp/_oc_tmp.json ~/.openclaw/openclaw.json"
    )


def cmd_delete_provider(provider_name: str) -> str:
    """构建 jq 命令：删除指定的 provider"""
    return (
        f"jq 'del(.models.providers[\"{provider_name}\"])' "
        f"~/.openclaw/openclaw.json > /tmp/_oc_tmp.json && "
        f"mv /tmp/_oc_tmp.json ~/.openclaw/openclaw.json"
    )
