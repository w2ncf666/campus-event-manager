# Windows local environment check. No installation, no network calls, no credentials read.
$ErrorActionPreference = 'Continue'
$root = Resolve-Path (Join-Path $PSScriptRoot '..')
$out = Join-Path $root 'docs/environment-report.local.md'
$items = @(
    @{Name='git'; Args=@('--version')},
    @{Name='node'; Args=@('--version')},
    @{Name='npm'; Args=@('--version')},
    @{Name='npx'; Args=@('--version')},
    @{Name='python'; Args=@('--version')},
    @{Name='uv'; Args=@('--version')},
    @{Name='codex'; Args=@('--version')}
)
$lines = [System.Collections.Generic.List[string]]::new()
$lines.Add('# 本机环境检查（仅本地，勿直接提交）')
$lines.Add('')
$lines.Add('检查日期：' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
$lines.Add('')
$lines.Add('| 工具 | 是否可找到 | 版本输出（第一行） |')
$lines.Add('| --- | --- | --- |')
foreach ($item in $items) {
    $cmd = Get-Command $item.Name -ErrorAction SilentlyContinue
    if ($null -eq $cmd) {
        $lines.Add('| ' + $item.Name + ' | 未找到 | - |')
    } else {
        try {
            $result = @(& $($item.Name) --version 2>&1)
            $first = ($result | Select-Object -First 1 | Out-String).Trim()
            if (-not $first) { $first = '已找到（无版本输出）' }
            $first = $first.Replace('|','/')
            $lines.Add('| ' + $item.Name + ' | 已找到 | ' + $first + ' |')
        } catch {
            $lines.Add('| ' + $item.Name + ' | 已找到 | 无法读取版本：' + $_.Exception.Message.Replace('|','/') + ' |')
        }
    }
}
$installed = Test-Path (Join-Path $root '_bmad')
$lines.Add('')
$lines.Add('本项目 `_bmad/` 目录存在：' + $(if ($installed) {'是'} else {'否（未验证本项目安装）'}))
$lines.Add('`bmad-help` 需要在支持的 AI 编程工具中手动检查：待检查')
$lines.Add('')
$lines.Add('请只将必要信息填写到 docs/team-environment.md。')
[System.IO.File]::WriteAllLines($out, $lines, [System.Text.UTF8Encoding]::new($false))
Write-Host 'Environment report generated:' $out
$lines | ForEach-Object { Write-Host $_ }
