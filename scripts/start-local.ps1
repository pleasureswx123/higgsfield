param(
    [ValidateSet('start', 'status')][string]$Action = 'start'
)
$ErrorActionPreference = 'Stop'
$backend = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../ruoyi-fastapi-backend'))
$runner = Join-Path $backend '.venv/Scripts/ruoyi.exe'
if (!(Test-Path -LiteralPath $runner)) { throw '请先安装后端虚拟环境与依赖。' }
$portLine = Get-Content -LiteralPath (Join-Path $backend '.env.dev') | Where-Object { $_ -match '^\s*APP_PORT\s*=\s*(\d+)' } | Select-Object -First 1
if (!$portLine -or $portLine -notmatch '=\s*(\d+)') { throw '请在后端 .env.dev 中配置 APP_PORT。' }
$apiPort = [int]$Matches[1]
if ($Action -eq 'status') {
    & (Join-Path $PSScriptRoot 'image-workers.ps1') -Action status
    $listening = Get-NetTCPConnection -LocalPort $apiPort -State Listen -ErrorAction SilentlyContinue
    Write-Output "API 端口 $apiPort : $(if ($listening) { '已监听（端口存在不代表业务健康）' } else { '未监听' })"
    return
}
# 工作器仅启动一次；API 热重载不经过此脚本，不会重启工作器。
& (Join-Path $PSScriptRoot 'image-workers.ps1') -Action start
if (Get-NetTCPConnection -LocalPort $apiPort -State Listen -ErrorAction SilentlyContinue) {
    Write-Output "端口 $apiPort 已被占用，保留现有进程，不重复启动 API。请确认现有服务是本工程 API。"
    return
}
Write-Output '正在启动 API。保持本终端开启；Ctrl+C 仅停止 API，工作器继续运行。'
Push-Location $backend
try {
    & $runner app run --env=dev
    if ($LASTEXITCODE -ne 0) { throw "API 退出，退出码 $LASTEXITCODE；工作器保持运行，可用 image-workers.ps1 查看或安全停止。" }
} finally { Pop-Location }
