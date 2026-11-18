#!/usr/bin/env bash
set -u
cd "$(dirname "$0")/.." || exit 1
out='docs/environment-report.local.md'
{
  echo '# 本机环境检查（仅本地，勿直接提交）'
  echo
  echo "检查日期：$(date '+%Y-%m-%d %H:%M:%S')"
  echo
  echo '| 工具 | 状态 | 版本输出（第一行） |'
  echo '| --- | --- | --- |'
  for name in git node npm npx python uv codex; do
    tool=$name
    if [[ $OSTYPE == msys* || $OSTYPE == cygwin* ]] && command -v "$name.exe" >/dev/null 2>&1; then
      tool="$name.exe"
    elif [[ $name == python ]] && command -v python3 >/dev/null 2>&1; then
      tool=python3
    fi
    if ! command -v "$tool" >/dev/null 2>&1; then
      printf '| %s | 未找到 | - |\n' "$name"
      continue
    fi

    if result=$("$tool" --version 2>&1); then
      status='可用'
    else
      status='执行失败'
    fi
    version=${result%%$'\n'*}
    version=${version%$'\r'}
    version=${version//|/\/}
    printf '| %s | %s | %s |\n' "$name" "$status" "${version:-无版本输出}"
  done
  echo
  if [[ -d _bmad ]]; then echo '本项目 `_bmad/` 目录存在：是'; else echo '本项目 `_bmad/` 目录存在：否（未验证本项目安装）'; fi
  echo '`bmad-help` 需要在支持的 AI 编程工具中手动检查：待检查'
} > "$out"
printf 'Environment report generated: %s\n' "$out"
cat "$out"
