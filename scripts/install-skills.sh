#!/usr/bin/env bash
# 安装 auto-epublizer Skill 到 opencode（或其他兼容 agent）。
#
# 用法：
#   ./scripts/install-skills.sh --target opencode
#
# 默认把 skills/auto-epublizer/ 复制到 agent 的 skills 目录。
set -euo pipefail

TARGET="opencode"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) TARGET="$2"; shift 2 ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/skills/auto-epublizer"

case "$TARGET" in
  opencode)
    DEST="${OPENCODE_SKILLS_DIR:-$HOME/.config/opencode/skills}/auto-epublizer"
    ;;
  *)
    echo "不支持的 target：$TARGET（目前支持 opencode）" >&2
    exit 2
    ;;
esac

mkdir -p "$(dirname "$DEST")"
rm -rf "$DEST"
cp -R "$SRC" "$DEST"
echo "已安装 Skill 到：$DEST"
