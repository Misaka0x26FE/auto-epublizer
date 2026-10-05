#!/usr/bin/env bash
# 安装 auto-epublizer Skill 到 opencode（或其他兼容 agent）。
#
# 用法：
#   ./scripts/install-skills.sh --target opencode
#   ./scripts/install-skills.sh --check     # 只校验 SKILL.md 是否合规，不安装
#
# 安装前先校验 SKILL.md 符合 Agent Skills / skills.sh 规范：
# frontmatter 置顶（首行 ---）+ name/description 齐备 + name 与目录同名 + description ≤1024。
set -euo pipefail

TARGET="opencode"
CHECK_ONLY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) TARGET="$2"; shift 2 ;;
    --check) CHECK_ONLY=1; shift ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/skills/auto-epublizer"
SKILL_MD="$SRC/SKILL.md"

if [[ ! -f "$SKILL_MD" ]]; then
  echo "缺少 $SKILL_MD" >&2
  exit 1
fi
if [[ "$(head -n1 "$SKILL_MD")" != "---" ]]; then
  echo "SKILL.md 必须以 YAML frontmatter（首行 ---）开头（skills.sh / Agent Skills 规范）" >&2
  exit 1
fi
name="$(sed -n 's/^name: //p' "$SKILL_MD" | head -n1)"
desc="$(sed -n 's/^description: //p' "$SKILL_MD" | head -n1)"
dir_name="$(basename "$SRC")"
if [[ -z "$name" || -z "$desc" ]]; then
  echo "SKILL.md frontmatter 缺 name/description（loaded 会报 missing required frontmatter）" >&2
  exit 1
fi
if [[ "$name" != "$dir_name" ]]; then
  echo "frontmatter name（$name）与目录名（$dir_name）不一致" >&2
  exit 1
fi
if (( ${#desc} > 1024 )); then
  echo "description 超过 1024 字符" >&2
  exit 1
fi
echo "SKILL.md 合规：name=$name（description ${#desc} 字符）"

if (( CHECK_ONLY )); then
  exit 0
fi

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
