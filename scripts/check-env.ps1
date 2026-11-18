# Windows local environment check. No installation, no network calls, no credentials read.
$ErrorActionPreference = 'Continue'
$root = Resolve-Path (Join-Path $PSScriptRoot '..')
$out = Join-Path $root 'docs/environment-report.local.md'
$commands = [ordered]@{
    git = 'git.exe'
    node = 'node.exe'
    npm = 'npm.cmd'
    npx = 'npx.cmd'
    python = 'python.exe'
    uv = 'uv.exe'
    codex = 'codex.exe'
}
$lines = [System.Collections.Generic.List[string]]::new()
$lines.Add('# 本机环境检查（仅本地，勿直接提交）')
$lines.Add('')
$lines.Add('检查日期：' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
$lines.Add('')
$lines.Add('| 工具 | 状态 | 版本输出（第一行） |')
$lines.Add('| --- | --- | --- |')
foreach ($item in $commands.GetEnumerator()) {
    $name = $item.Key
    $cmd = Get-Command $item.Value -ErrorAction SilentlyContinue
    if ($null -eq $cmd) {
        $lines.Add("| $name | 未找到 | - |")
        continue
    }

    try {
        $result = @(& $cmd.Source --version 2>$null)
        if ($LASTEXITCODE -ne 0) {
            $lines.Add("| $name | 执行失败 | 退出码 $LASTEXITCODE |")
            continue
        }
        $first = ($result | Select-Object -First 1 | Out-String).Trim().Replace('|','/')
        if (-not $first) { $first = '无版本输出' }
        $lines.Add("| $name | 可用 | $first |")
    } catch {
        $message = ($_.Exception.Message -split '\r?\n')[0].Replace('|','/')
        $lines.Add("| $name | 执行失败 | $message |")
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
