#!/usr/bin/env bash
# ============================================================
# ShareClaw — 云服务器一键部署脚本
#
# 用法:
#   curl -fsSL https://raw.githubusercontent.com/GardenChan/ShareClaw/main/scripts/deploy.sh | bash
#   或：
#   bash deploy.sh
#
# 支持:
#   - Ubuntu 20.04 / 22.04 / 24.04
#   - Debian 11 / 12
#   - CentOS Stream 8/9, Rocky/Alma Linux
#   - 本地模式 (local) 和远程模式 (remote)
# ============================================================

set -euo pipefail

# ── 颜色 ─────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }
ask()   { echo -en "${BOLD}$*${NC}"; }

# ── 全局变量 ──────────────────────────────────────────────
INSTALL_DIR="/opt/shareclaw"
VENV_DIR="$INSTALL_DIR/venv"
DEPLOY_USER="$(whoami)"
HOME_DIR="$(eval echo ~$DEPLOY_USER)"
CONFIG_DIR="$HOME_DIR/.config/shareclaw"
SYSTEMD_DIR="$HOME_DIR/.config/systemd/user"
PORT=9000

# ── 系统检测 ──────────────────────────────────────────────
detect_os() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        OS_ID="${ID,,}"
        OS_VERSION="${VERSION_ID}"
    else
        error "无法检测操作系统，请使用 Ubuntu/Debian/CentOS"
    fi
}

detect_pkg_manager() {
    if command -v apt-get &>/dev/null; then
        PKG="apt-get"
        PKG_INSTALL="apt-get install -y"
        PKG_UPDATE="apt-get update -y"
    elif command -v dnf &>/dev/null; then
        PKG="dnf"
        PKG_INSTALL="dnf install -y"
        PKG_UPDATE="dnf check-update || true"
    elif command -v yum &>/dev/null; then
        PKG="yum"
        PKG_INSTALL="yum install -y"
        PKG_UPDATE="yum check-update || true"
    else
        error "未找到包管理器 (apt/dnf/yum)"
    fi
}

# ── 欢迎 ─────────────────────────────────────────────────
show_banner() {
    echo ""
    echo -e "${RED}  ____  _                     ____ _"
    echo -e " / ___|| |__   __ _ _ __ ___ / ___| | __ ___      __"
    echo -e " \\___ \\| '_ \\ / _\` | '__/ _ \\ |   | |/ _\` \\ \\ /\\ / /"
    echo -e "  ___) | | | | (_| | | |  __/ |___| | (_| |\\ V  V /"
    echo -e " |____/|_| |_|\\__,_|_|  \\___|\\____|_|\\__,_| \\_/\\_/${NC}"
    echo ""
    echo -e "  ${BOLD}拼虾虾 — 云服务器一键部署${NC}"
    echo -e "  ${CYAN}https://github.com/GardenChan/ShareClaw${NC}"
    echo ""
    echo "─────────────────────────────────────────────"
    echo ""
}

# ── 模式选择 ──────────────────────────────────────────────
choose_mode() {
    echo -e "${BOLD}请选择部署模式：${NC}"
    echo ""
    echo "  1) local  — ShareClaw 与 OpenClaw 在同一台服务器"
    echo "  2) remote — ShareClaw 独立部署，通过腾讯云 TAT 远程管理 OpenClaw"
    echo ""
    ask "请输入 [1/2] (默认 1): "
    read -r mode_choice
    echo ""

    case "${mode_choice:-1}" in
        1|local)  DEPLOY_MODE="local" ;;
        2|remote) DEPLOY_MODE="remote" ;;
        *) DEPLOY_MODE="local" ;;
    esac
    ok "部署模式: $DEPLOY_MODE"
}

# ── CPU 核数检测与队列推荐 ─────────────────────────────────
#
# openclaw-gateway 是一个 Node.js 单进程（事件驱动），所有微信号共享同一个进程。
# 每个 queue slot = 一个已登录的微信号，增加的负载主要是：
#   - WebSocket 长连接维护
#   - 消息并发处理（解析、转发到 AI API）
#   - 插件执行（openclaw-weixin 消息收发）
#
# AI 推理本身调用外部 API（如 OpenAI/Anthropic），不消耗本地 CPU。
# 微信号大部分时间处于空闲（等待消息），不会同时活跃，实际并发很低。
#
# 推荐规则：CPU 核数 × 2
#
# 微信号大部分时间处于空闲状态（等待消息），不会同时活跃，
# 实际并发远低于在线号数，因此按 2 倍核数推荐即可。
# 例：2 核 → 4，4 核 → 8，8 核 → 16
#
recommend_queue_size() {
    local cpu_cores
    cpu_cores="$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 0)"

    if [[ "$cpu_cores" -le 0 ]]; then
        echo 6  # 无法检测时使用默认值
        return
    fi

    echo $(( cpu_cores * 2 ))
}

# ── 收集配置 ──────────────────────────────────────────────
collect_local_config() {
    OPENCLAW_HOME="${HOME_DIR}/.openclaw"
    SHARECLAW_HOME="${HOME_DIR}/.shareclaw"

    ask "OpenClaw 主目录 (默认 $OPENCLAW_HOME): "
    read -r input
    [[ -n "$input" ]] && OPENCLAW_HOME="$input"

    ask "ShareClaw 数据目录 (默认 $SHARECLAW_HOME): "
    read -r input
    [[ -n "$input" ]] && SHARECLAW_HOME="$input"

    local cpu_cores
    cpu_cores="$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo '?')"
    local recommended
    recommended="$(recommend_queue_size)"
    info "检测到 CPU: ${cpu_cores} 核，推荐队列长度: ${recommended}"
    ask "队列最大长度 (推荐 $recommended，直接回车使用推荐值): "
    read -r input
    MAX_QUEUE="${input:-$recommended}"

    ask "监听端口 (默认 9000): "
    read -r input
    PORT="${input:-9000}"

    ask "虾主管理密码 (默认 pinxiaxia): "
    read -r input
    ADMIN_PASSWORD="${input:-pinxiaxia}"
    echo ""
}

collect_remote_config() {
    ask "腾讯云 SecretId: "
    read -r SECRET_ID
    [[ -z "$SECRET_ID" ]] && error "SecretId 不能为空"

    ask "腾讯云 SecretKey: "
    read -r SECRET_KEY
    [[ -z "$SECRET_KEY" ]] && error "SecretKey 不能为空"

    ask "Lighthouse 实例 ID (多个用逗号分隔): "
    read -r INSTANCE_IDS
    [[ -z "$INSTANCE_IDS" ]] && error "实例 ID 不能为空"

    ask "Lighthouse 地域 (默认 ap-guangzhou): "
    read -r input
    REGION="${input:-ap-guangzhou}"

    SHARECLAW_HOME="${HOME_DIR}/.shareclaw"

    # 远程模式：队列上限是每台远程实例各自的上限，
    # 瓶颈在远程实例的资源，需要按远程实例的 CPU 核数来推荐
    ask "远程 Lighthouse 实例的 CPU 核数 (单台): "
    read -r remote_cpu
    if [[ -n "$remote_cpu" ]] && [[ "$remote_cpu" -gt 0 ]] 2>/dev/null; then
        local recommended=$(( remote_cpu * 2 ))
        info "远程实例 CPU: ${remote_cpu} 核，推荐每台队列长度: ${recommended}"
        ask "每台实例的队列最大长度 (推荐 $recommended，直接回车使用推荐值): "
        read -r input
        MAX_QUEUE="${input:-$recommended}"
    else
        info "未输入远程实例 CPU 核数，使用默认值"
        ask "每台实例的队列最大长度 (默认 6): "
        read -r input
        MAX_QUEUE="${input:-6}"
    fi

    ask "监听端口 (默认 9000): "
    read -r input
    PORT="${input:-9000}"

    ask "虾主管理密码 (默认 pinxiaxia): "
    read -r input
    ADMIN_PASSWORD="${input:-pinxiaxia}"
    echo ""
}

# ── 安装系统依赖 ──────────────────────────────────────────
install_deps() {
    info "安装系统依赖..."

    if [[ "$DEPLOY_USER" == "root" ]]; then
        $PKG_UPDATE
        $PKG_INSTALL python3 python3-venv python3-pip nginx curl
    else
        sudo $PKG_UPDATE
        sudo $PKG_INSTALL python3 python3-venv python3-pip nginx curl
    fi

    ok "系统依赖安装完成"
}

# ── 本地模式前置检查 ──────────────────────────────────────
check_local_prereqs() {
    info "检查本地模式前置条件..."

    # 检查 node 命令（openclaw 依赖 Node.js）
    if ! command -v node &>/dev/null; then
        warn "未找到 node 命令，OpenClaw 依赖 Node.js 运行"
        warn "请安装 Node.js: https://nodejs.org/ 或通过 nvm 安装"
    else
        ok "node 命令可用: $(which node) ($(node --version))"
    fi

    # 检查 openclaw 命令
    if ! command -v openclaw &>/dev/null; then
        warn "未找到 openclaw 命令，轮转功能可能无法正常使用"
        warn "请确保 OpenClaw 已安装并在 PATH 中"
    else
        ok "openclaw 命令可用: $(which openclaw)"
    fi

    # 检查 openclaw.json
    if [[ -f "$OPENCLAW_HOME/openclaw.json" ]]; then
        ok "openclaw.json 存在"
    else
        warn "$OPENCLAW_HOME/openclaw.json 不存在，请确认 OpenClaw 已配置"
    fi

    # 检查 gateway
    if systemctl --user is-active openclaw-gateway &>/dev/null; then
        ok "openclaw-gateway 状态: active"
    else
        warn "openclaw-gateway 未运行或不是用户级服务"
    fi
}

# ── 安装 ShareClaw ────────────────────────────────────────
install_shareclaw() {
    info "安装 ShareClaw..."

    # 创建目录
    if [[ "$DEPLOY_USER" == "root" ]]; then
        mkdir -p "$INSTALL_DIR"
    else
        sudo mkdir -p "$INSTALL_DIR"
        sudo chown -R "$DEPLOY_USER:$(id -gn)" "$INSTALL_DIR"
    fi

    # 创建虚拟环境
    if [[ ! -d "$VENV_DIR" ]]; then
        info "创建 Python 虚拟环境..."
        python3 -m venv "$VENV_DIR"
    fi

    # 从 PyPI 安装
    info "从 PyPI 安装 shareclaw..."
    "$VENV_DIR/bin/pip" install -U pip -q
    "$VENV_DIR/bin/pip" install -U shareclaw -q

    # 验证
    VERSION=$("$VENV_DIR/bin/python" -c "from shareclaw import __version__; print(__version__)")
    ok "ShareClaw v$VERSION 安装完成 (from PyPI)"
}

# ── 写入环境变量 ──────────────────────────────────────────
write_env_file() {
    info "写入环境变量配置..."

    mkdir -p "$CONFIG_DIR"
    mkdir -p "$SHARECLAW_HOME"

    local ENV_FILE="$CONFIG_DIR/shareclaw.env"

    cat > "$ENV_FILE" <<ENVEOF
# ShareClaw 环境变量 (由部署脚本自动生成)
SHARECLAW_MODE=$DEPLOY_MODE
SHARECLAW_MAX_QUEUE_SIZE=$MAX_QUEUE
SHARECLAW_HOME=$SHARECLAW_HOME
PORT=$PORT
ENVEOF

    if [[ "$DEPLOY_MODE" == "local" ]]; then
        cat >> "$ENV_FILE" <<ENVEOF
# 仅用于 ShareClaw 主进程定位 openclaw 配置文件（accounts.json 等），
# 不会传递给 openclaw 子进程（子进程通过 bash login shell 自行推导）。
OPENCLAW_HOME=$OPENCLAW_HOME
ENVEOF
    else
        cat >> "$ENV_FILE" <<ENVEOF
TENCENT_SECRET_ID=$SECRET_ID
TENCENT_SECRET_KEY=$SECRET_KEY
LIGHTHOUSE_INSTANCE_IDS=$INSTANCE_IDS
LIGHTHOUSE_REGION=$REGION
ENVEOF
    fi

    if [[ -n "${ADMIN_PASSWORD:-}" ]]; then
        echo "SHARECLAW_ADMIN_PASSWORD=$ADMIN_PASSWORD" >> "$ENV_FILE"
    fi

    chmod 600 "$ENV_FILE"
    ok "环境变量已写入: $ENV_FILE"
}

# ── 配置 systemd 服务 ─────────────────────────────────────
setup_systemd() {
    info "配置 systemd 用户级服务..."

    mkdir -p "$SYSTEMD_DIR"

    # 构建 PATH
    # ShareClaw 的 openclaw 子命令通过 bash -lc（login shell）执行，
    # 会自动从 ~/.bashrc / ~/.profile 加载 nvm/pnpm 等环境，
    # 因此 systemd PATH 只需包含 venv 和基本系统路径即可。
    local SVC_PATH="$VENV_DIR/bin:${HOME_DIR}/.local/bin:/usr/local/bin:/usr/bin:/bin"

    cat > "$SYSTEMD_DIR/shareclaw.service" <<SVCEOF
[Unit]
Description=ShareClaw Web Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=$CONFIG_DIR/shareclaw.env
Environment=PATH=$SVC_PATH
WorkingDirectory=$INSTALL_DIR
ExecStart=$VENV_DIR/bin/shareclaw serve --host 127.0.0.1 --port $PORT
Restart=always
RestartSec=3
TimeoutStopSec=20

[Install]
WantedBy=default.target
SVCEOF

    systemctl --user daemon-reload
    systemctl --user enable shareclaw
    systemctl --user restart shareclaw

    # 启用 linger（开机自启）
    if [[ "$DEPLOY_USER" == "root" ]]; then
        loginctl enable-linger root 2>/dev/null || true
    else
        sudo loginctl enable-linger "$DEPLOY_USER" 2>/dev/null || true
    fi

    # 等待启动
    sleep 2

    if systemctl --user is-active shareclaw &>/dev/null; then
        ok "shareclaw 服务已启动"
    else
        warn "shareclaw 服务启动可能有问题，请检查:"
        warn "  journalctl --user -u shareclaw -n 20"
    fi
}

# ── 配置 Nginx ────────────────────────────────────────────
setup_nginx() {
    info "配置 Nginx 反向代理..."

    local NGINX_CONF="/etc/nginx/sites-available/shareclaw"
    local NGINX_LINK="/etc/nginx/sites-enabled/shareclaw"

    # 检查 sites-available 是否存在（CentOS 没有）
    if [[ ! -d /etc/nginx/sites-available ]]; then
        if [[ "$DEPLOY_USER" == "root" ]]; then
            mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled
        else
            sudo mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled
        fi
        # 确保 nginx.conf 包含 sites-enabled
        if ! grep -q "sites-enabled" /etc/nginx/nginx.conf 2>/dev/null; then
            if [[ "$DEPLOY_USER" == "root" ]]; then
                sed -i '/http {/a \    include /etc/nginx/sites-enabled/*;' /etc/nginx/nginx.conf
            else
                sudo sed -i '/http {/a \    include /etc/nginx/sites-enabled/*;' /etc/nginx/nginx.conf
            fi
        fi
    fi

    local NGINX_CONTENT
    read -r -d '' NGINX_CONTENT <<'NGXEOF' || true
server {
    listen 80;
    server_name _;

    # SSE 流式接口 — 必须关闭缓冲
    location /rotate {
        proxy_pass http://127.0.0.1:__PORT__;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
        add_header X-Accel-Buffering no;
    }

    # 其他接口
    location / {
        proxy_pass http://127.0.0.1:__PORT__;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }
}
NGXEOF

    NGINX_CONTENT="${NGINX_CONTENT//__PORT__/$PORT}"

    if [[ "$DEPLOY_USER" == "root" ]]; then
        echo "$NGINX_CONTENT" > "$NGINX_CONF"
        ln -sf "$NGINX_CONF" "$NGINX_LINK"
        # 移除默认站点（避免冲突）
        rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
        nginx -t && systemctl reload nginx
    else
        echo "$NGINX_CONTENT" | sudo tee "$NGINX_CONF" > /dev/null
        sudo ln -sf "$NGINX_CONF" "$NGINX_LINK"
        sudo rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
        sudo nginx -t && sudo systemctl reload nginx
    fi

    ok "Nginx 反向代理已配置 (80 → 127.0.0.1:$PORT)"
}

# ── 健康检查 ──────────────────────────────────────────────
final_check() {
    echo ""
    info "执行部署验证..."
    echo ""

    # 直连检查
    local direct_ok=false
    for i in 1 2 3; do
        if curl -sf "http://127.0.0.1:$PORT/health" &>/dev/null; then
            direct_ok=true
            break
        fi
        sleep 1
    done

    if $direct_ok; then
        ok "直连检查通过: http://127.0.0.1:$PORT/health"
    else
        warn "直连检查失败，请检查服务日志"
    fi

    # Nginx 检查
    if curl -sf "http://127.0.0.1/health" &>/dev/null; then
        ok "Nginx 代理检查通过: http://127.0.0.1/health"
    else
        warn "Nginx 代理检查未通过（可能需要手动调整配置）"
    fi

    # 获取公网 IP
    local PUBLIC_IP
    PUBLIC_IP=$(curl -sf --max-time 5 https://ifconfig.me 2>/dev/null || curl -sf --max-time 5 https://api.ipify.org 2>/dev/null || echo "")

    echo ""
    echo "═════════════════════════════════════════════"
    echo ""
    echo -e "  ${GREEN}${BOLD}部署完成！${NC}"
    echo ""
    echo -e "  部署模式:   ${BOLD}$DEPLOY_MODE${NC}"
    echo -e "  版本:       ${BOLD}v$VERSION${NC}"
    echo -e "  服务端口:   ${BOLD}$PORT${NC}"
    echo ""
    if [[ -n "$PUBLIC_IP" ]]; then
        echo -e "  ${BOLD}访问地址:${NC}"
        echo -e "    接入页:     http://$PUBLIC_IP"
        echo -e "    管理面板:   http://$PUBLIC_IP/dashboard"
        echo -e "    健康检查:   http://$PUBLIC_IP/health"
    else
        echo -e "  ${BOLD}访问地址:${NC}"
        echo -e "    http://127.0.0.1:$PORT"
    fi
    echo ""
    echo -e "  ${BOLD}常用命令:${NC}"
    echo -e "    查看状态:   systemctl --user status shareclaw"
    echo -e "    查看日志:   journalctl --user -u shareclaw -f"
    echo -e "    重启服务:   systemctl --user restart shareclaw"
    echo -e "    编辑配置:   nano $CONFIG_DIR/shareclaw.env"
    echo ""
    echo "═════════════════════════════════════════════"
    echo ""
}

# ── 主流程 ────────────────────────────────────────────────
main() {
    show_banner
    detect_os
    detect_pkg_manager

    info "操作系统: $OS_ID $OS_VERSION"
    info "部署用户: $DEPLOY_USER"
    info "用户目录: $HOME_DIR"
    echo ""

    # 1. 选择模式
    choose_mode

    # 2. 收集配置
    if [[ "$DEPLOY_MODE" == "local" ]]; then
        collect_local_config
    else
        collect_remote_config
    fi

    echo ""
    info "开始部署..."
    echo ""

    # 3. 安装系统依赖
    install_deps

    # 4. 本地模式前置检查
    if [[ "$DEPLOY_MODE" == "local" ]]; then
        check_local_prereqs
    fi

    # 5. 安装 ShareClaw
    install_shareclaw

    # 6. 写入环境变量
    write_env_file

    # 7. 配置 systemd 服务
    setup_systemd

    # 8. 配置 Nginx
    setup_nginx

    # 9. 最终验证
    final_check
}

main "$@"
