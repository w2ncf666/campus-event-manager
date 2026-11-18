#!/usr/bin/env bash
set -u
cd "$(dirname "$0")/.." || exit 1
out='docs/environment-report.local.md'
{
  echo '# 本机环境检查（仅本地，勿直接提交）'
  echo
  echo "检查日期：$(date '+%Y-%m-%d %H:%M:%S')"
  echo
  echo '| 工具 | 是否可找到 | 版本输出（第一行） |'
  echo '| --- | --- | --- |'
  for name in git node npm npx python uv codex; do
    if command -v "$name" >/dev/null 2>&1; then
      result=$("$name" --version 2>&1 | head -n 1 | tr '|' '/' || true)
      printf '| %s | 已找到 | %s |\n' "$name" "${result:-已找到（无版本输出）}"
    else
      printf '| %s | 未找到 | - |\n' "$name"
    fi
  done
  echo
  if [[ -d _bmad ]]; then echo '本项目 `_bmad/` 目录存在：是'; else echo '本项目 `_bmad/` 目录存在：否（未验证本项目安装）'; fi
  echo '`bmad-help` 需要在支持的 AI 编程工具中手动检查：待检查'
} > "$out"
printf 'Environment report generated: %s\n' "$out"
cat "$out"
