#!/usr/bin/env bash
# HERMES Flow (hermes_flow) 插件安装脚本 —— Linux / macOS。
# 默认用符号链接把插件根挂到 $HERMES_HOME/plugins/hermes_flow；--copy 则复制。
# 幂等：已指向当前目录时跳过；指向别处时先备份再重建。
#
# 用法：
#   bash install.sh
#   HERMES_HOME=/opt/hermes bash install.sh
#   bash install.sh --copy
#   bash install.sh --enable
#
# 编码：UTF-8（无 BOM）。

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
COPY_MODE=0
DO_ENABLE=0

usage() {
  cat <<'EOF'
用法: bash install.sh [--copy] [--enable] [--home PATH] [--help]

  --copy        不使用符号链接，复制插件文件（跨文件系统或权限受限时使用）
  --enable      安装后尝试执行 hermes plugins enable hermes_flow
  --home PATH   指定 HERMES_HOME（默认 $HERMES_HOME 或 ~/.hermes）
  --help        显示本帮助
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --copy) COPY_MODE=1 ;;
    --enable) DO_ENABLE=1 ;;
    --home)
      shift
      [ $# -gt 0 ] || { echo "错误: --home 需要一个路径" >&2; exit 2; }
      HERMES_HOME="$1"
      ;;
    -h|--help) usage; exit 0 ;;
    *) echo "错误: 未知参数 $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

step() { printf '\033[36m[hermes_flow] %s\033[0m\n' "$1"; }
ok()   { printf '\033[32m[hermes_flow] %s\033[0m\n' "$1"; }
warn() { printf '\033[33m[hermes_flow] %s\033[0m\n' "$1"; }

# ---------------------------------------------------------------------------
# 1. 源目录与插件完整性
# ---------------------------------------------------------------------------
for item in plugin.yaml flow_core tools.py runtime.py __init__.py agents skills workflows; do
  if [ ! -e "$SCRIPT_DIR/$item" ]; then
    echo "错误: 当前目录不是 hermes_flow 插件根，缺少 $item（目录：$SCRIPT_DIR）" >&2
    exit 1
  fi
done
step "源目录：$SCRIPT_DIR"

# ---------------------------------------------------------------------------
# 2. 校验 Python 可用（插件内核与 CLI 依赖 Python 3.9+）
# ---------------------------------------------------------------------------
PYTHON_BIN=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
      PYTHON_BIN="$candidate"
      break
    fi
  fi
done
if [ -z "$PYTHON_BIN" ]; then
  echo "错误: 未找到 Python 3.9+。请先安装 Python 并加入 PATH。" >&2
  exit 1
fi
ok "Python 可用：$("$PYTHON_BIN" --version 2>&1)（$PYTHON_BIN）"

# ---------------------------------------------------------------------------
# 3. 目标目录：$HERMES_HOME/plugins/hermes_flow
# ---------------------------------------------------------------------------
case "$HERMES_HOME" in
  "~") HERMES_HOME="$HOME" ;;
  "~/"*) HERMES_HOME="$HOME/${HERMES_HOME#\~/}" ;;
esac
if [ ! -d "$HERMES_HOME" ]; then
  echo "错误: HERMES_HOME 不存在：$HERMES_HOME。请先安装/初始化 Hermes，或用 --home 指定。" >&2
  exit 1
fi
PLUGINS_DIR="$HERMES_HOME/plugins"
mkdir -p "$PLUGINS_DIR"
TARGET="$PLUGINS_DIR/hermes_flow"
step "目标：$TARGET"

same_target=0
if [ -e "$TARGET" ] || [ -L "$TARGET" ]; then
  if [ -L "$TARGET" ]; then
    link_target="$(cd -P -- "$(dirname -- "$TARGET")" && pwd)/$(readlink "$TARGET")" || link_target=""
    if [ -n "$link_target" ] && [ "$(cd -P -- "$link_target" 2>/dev/null && pwd)" = "$SCRIPT_DIR" ]; then
      same_target=1
    fi
  elif [ -e "$TARGET/plugin.yaml" ] && [ "$TARGET/plugin.yaml" -ef "$SCRIPT_DIR/plugin.yaml" ]; then
    # MSYS/Cygwin 的 ln -s 对目录可能退化为 junction：用 -ef 判断是否同一 inode
    same_target=1
  fi
  if [ "$same_target" -eq 0 ]; then
    BACKUP_ROOT="$HERMES_HOME/backups"
    mkdir -p "$BACKUP_ROOT"
    BACKUP="$BACKUP_ROOT/hermes_flow-$(date +%Y%m%d-%H%M%S)"
    warn "目标已存在且不是当前源目录，移动到备份：$BACKUP"
    mv "$TARGET" "$BACKUP"
  fi
fi

if [ "$same_target" -eq 1 ]; then
  ok "已安装且指向当前目录，跳过链接创建（幂等）。"
elif [ "$COPY_MODE" -eq 1 ]; then
  mkdir -p "$TARGET"
  step "复制文件到 $TARGET ..."
  cp -R "$SCRIPT_DIR/." "$TARGET/"
  ok "复制完成（源目录后续修改不会自动同步）。"
else
  if ln -s "$SCRIPT_DIR" "$TARGET" 2>/dev/null; then
    if [ -L "$TARGET" ] || { [ -e "$TARGET/plugin.yaml" ] && [ "$TARGET/plugin.yaml" -ef "$SCRIPT_DIR/plugin.yaml" ]; }; then
      ok "已创建符号链接/目录联接（源码改动即时生效）。"
    else
      warn "当前文件系统的 ln -s 退化为复制，后续源改动需重新执行安装。"
    fi
  else
    warn "创建符号链接失败，回退为复制。"
    mkdir -p "$TARGET"
    cp -R "$SCRIPT_DIR/." "$TARGET/"
  fi
fi

# ---------------------------------------------------------------------------
# 4. 启用与验证提示
# ---------------------------------------------------------------------------
DATA_DIR="$HERMES_HOME/plugin-data/hermes_flow"
printf '\n'
ok "安装完成。"
printf '  插件根：%s\n' "$TARGET"
printf '  数据目录：%s（首次运行自动创建）\n' "$DATA_DIR"
printf '\n下一步：\n'
printf '  1) hermes plugins enable hermes_flow\n'
printf '  2) hermes flow status\n'
printf '  3) hermes flow agents / hermes flow skills / hermes flow workflows\n'
printf '  4) hermes flow demo --files 287\n\n'

if [ "$DO_ENABLE" -eq 1 ]; then
  if command -v hermes >/dev/null 2>&1; then
    step "执行 hermes plugins enable hermes_flow ..."
    hermes plugins enable hermes_flow || warn "启用命令返回非零，请手动检查。"
  else
    warn "未找到 hermes 命令，请手动执行：hermes plugins enable hermes_flow"
  fi
elif ! command -v hermes >/dev/null 2>&1; then
  warn "未在 PATH 找到 hermes 命令；请在 Hermes 环境中执行启用命令。"
fi

printf '提示：Hermes 已运行中的话，重启服务或新开会话后插件才会被加载。\n'
