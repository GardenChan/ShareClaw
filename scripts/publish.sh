#!/usr/bin/env bash
# ============================================================
# ShareClaw — 自动打包 & 上传 PyPI 脚本
# 用法:
#   ./scripts/publish.sh          # 上传到正式 PyPI
#   ./scripts/publish.sh --test   # 上传到 TestPyPI
#   ./scripts/publish.sh --dry    # 仅构建，不上传
#   ./scripts/publish.sh --bump patch  # 自动升版本后上传
# ============================================================

set -euo pipefail

# ---- 颜色 ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # 无颜色

# ---- 工具函数 ----
info()  { echo -e "${CYAN}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ---- 切换到项目根目录 ----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"
info "项目根目录: $PROJECT_ROOT"

# ---- 解析参数 ----
TARGET="pypi"       # pypi | testpypi | dry
BUMP=""             # major | minor | patch | ""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --test)
            TARGET="testpypi"
            shift
            ;;
        --dry)
            TARGET="dry"
            shift
            ;;
        --bump)
            BUMP="$2"
            shift 2
            ;;
        -h|--help)
            echo "用法: $0 [--test] [--dry] [--bump major|minor|patch]"
            echo ""
            echo "选项:"
            echo "  --test              上传到 TestPyPI（测试仓库）"
            echo "  --dry               仅构建，不上传"
            echo "  --bump <level>      自动升版本号 (major / minor / patch)"
            echo "  -h, --help          显示帮助信息"
            exit 0
            ;;
        *)
            error "未知参数: $1，使用 --help 查看帮助"
            ;;
    esac
done

# ---- 检查依赖工具 ----
info "检查依赖工具..."
for cmd in python3 pip; do
    if ! command -v "$cmd" &>/dev/null; then
        error "未找到 $cmd，请先安装"
    fi
done

# 确保 build 和 twine 已安装
python3 -m pip install --quiet --upgrade build twine
ok "build & twine 已就绪"

# ---- 自动升版本 ----
TOML_FILE="$PROJECT_ROOT/pyproject.toml"

get_version() {
    grep -E '^version\s*=' "$TOML_FILE" | head -1 | sed 's/.*"\(.*\)".*/\1/'
}

bump_version() {
    local current="$1"
    local level="$2"
    local major minor patch

    IFS='.' read -r major minor patch <<< "$current"

    case "$level" in
        major) major=$((major + 1)); minor=0; patch=0 ;;
        minor) minor=$((minor + 1)); patch=0 ;;
        patch) patch=$((patch + 1)) ;;
        *) error "无效的版本级别: $level (可选: major / minor / patch)" ;;
    esac

    echo "$major.$minor.$patch"
}

CURRENT_VERSION="$(get_version)"
info "当前版本: v$CURRENT_VERSION"

if [[ -n "$BUMP" ]]; then
    NEW_VERSION="$(bump_version "$CURRENT_VERSION" "$BUMP")"
    info "升级版本: v$CURRENT_VERSION -> v$NEW_VERSION ($BUMP)"

    # 更新 pyproject.toml 中的版本号
    if [[ "$(uname)" == "Darwin" ]]; then
        sed -i '' "s/^version = \"$CURRENT_VERSION\"/version = \"$NEW_VERSION\"/" "$TOML_FILE"
    else
        sed -i "s/^version = \"$CURRENT_VERSION\"/version = \"$NEW_VERSION\"/" "$TOML_FILE"
    fi

    # 更新 __init__.py 中的版本号（如果存在）
    INIT_FILE="$PROJECT_ROOT/shareclaw/__init__.py"
    if [[ -f "$INIT_FILE" ]] && grep -q "__version__" "$INIT_FILE"; then
        if [[ "$(uname)" == "Darwin" ]]; then
            sed -i '' "s/__version__ = \"$CURRENT_VERSION\"/__version__ = \"$NEW_VERSION\"/" "$INIT_FILE"
        else
            sed -i "s/__version__ = \"$CURRENT_VERSION\"/__version__ = \"$NEW_VERSION\"/" "$INIT_FILE"
        fi
        ok "已更新 shareclaw/__init__.py 版本号"
    fi

    CURRENT_VERSION="$NEW_VERSION"
    ok "已更新 pyproject.toml 版本号为 v$CURRENT_VERSION"
fi

# ---- 清理旧的构建产物 ----
info "清理旧的构建产物..."
rm -rf dist/ build/ *.egg-info shareclaw/*.egg-info
ok "清理完成"

# ---- 构建 ----
info "开始构建 v$CURRENT_VERSION ..."
python3 -m build
ok "构建完成"

# 展示构建产物
echo ""
info "构建产物:"
ls -lh dist/
echo ""

# ---- 检查包 ----
info "检查包的合规性..."
python3 -m twine check dist/*
ok "包检查通过"

# ---- 上传 ----
case "$TARGET" in
    dry)
        warn "仅构建模式 (--dry)，跳过上传"
        ok "构建产物位于 dist/ 目录"
        ;;
    testpypi)
        info "上传到 TestPyPI..."
        python3 -m twine upload --repository testpypi dist/*
        echo ""
        ok "上传成功！"
        info "测试安装命令:"
        echo "  pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ shareclaw==$CURRENT_VERSION"
        ;;
    pypi)
        echo ""
        warn "即将上传到 正式 PyPI，版本: v$CURRENT_VERSION"
        read -rp "确认上传？(y/N) " confirm
        if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
            warn "已取消上传"
            exit 0
        fi
        info "上传到 PyPI..."
        python3 -m twine upload dist/*
        echo ""
        ok "上传成功！🎉"
        info "安装命令:"
        echo "  pip install shareclaw==$CURRENT_VERSION"
        ;;
esac

echo ""
ok "全部完成！"
