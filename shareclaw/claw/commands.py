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
