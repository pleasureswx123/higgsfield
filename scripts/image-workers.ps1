param(
    [ValidateSet('start', 'status', 'stop')]
    [string]$Action = 'status'
)
$ErrorActionPreference = 'Stop'
$backend = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../ruoyi-fastapi-backend'))
$python = Join-Path $backend '.venv/Scripts/python.exe'
$logs = Join-Path $backend 'output/image-workers'
$statePath = Join-Path $logs 'processes.json'
$modes = @('image', 'image-recovery', 'video', 'archive', 'billing', 'image-thumbnail', 'credential-test')

function Get-OwnedWorker($entry) {
    $candidate = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$entry.id)" -ErrorAction SilentlyContinue
    if ($candidate -and $candidate.ExecutablePath -eq $python -and
        $candidate.CommandLine -like '*module_higgsfield.worker*' -and
        $candidate.CommandLine -match "--mode $([regex]::Escape($entry.mode))( |$)" -and
        $candidate.CommandLine -like '*--worker-id manual-image-*') { return $candidate }
    return $null
}

$saved = @()
# Windows PowerShell 5.1 的 JSON 数组输出不可再套管道数组表达式，否则会成为嵌套数组。
if (Test-Path -LiteralPath $statePath) { $saved = ConvertFrom-Json -InputObject (Get-Content -LiteralPath $statePath -Raw -Encoding UTF8) }
if ($Action -eq 'status') {
    foreach ($mode in $modes) {
        $entry = $saved | Where-Object { $_.mode -eq $mode } | Select-Object -First 1
        $running = $entry -and (Get-OwnedWorker $entry)
        Write-Output "$mode : $(if ($running) { '运行中，PID ' + $entry.id } else { '未运行' })"
    }
    Write-Output "日志目录：$logs"
    exit
}
if ($Action -eq 'stop') {
    foreach ($entry in $saved) {
        if (Get-OwnedWorker $entry) {
            # 虚拟环境启动器另有实际 Python 子进程，必须一并停止，避免旧代码继续消费任务。
            $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $([int]$entry.id)" -ErrorAction SilentlyContinue
            foreach ($child in $children) {
                if ($child.CommandLine -like '*module_higgsfield.worker*' -and
                    $child.CommandLine -match "--mode $([regex]::Escape($entry.mode))( |$)" -and
                    $child.CommandLine -like '*--worker-id manual-image-*') {
                    Stop-Process -Id $child.ProcessId -ErrorAction SilentlyContinue
                }
            }
            Stop-Process -Id $entry.id -ErrorAction SilentlyContinue
        }
    }
    Write-Output '已停止本脚本启动的工作器。执行中的供应商请求可能转为结果待确认，不会自动重发。'
    exit
}
if (!(Test-Path -LiteralPath $python)) { throw '未找到后端虚拟环境。' }
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$current = @()
foreach ($mode in $modes) {
    $entry = $saved | Where-Object { $_.mode -eq $mode } | Select-Object -First 1
    if ($entry -and (Get-OwnedWorker $entry)) { $current += $entry; continue }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $workerProcess = Start-Process -FilePath $python -WorkingDirectory $backend -WindowStyle Hidden -PassThru `
        -ArgumentList @('-m', 'module_higgsfield.worker', '--mode', $mode, '--env', 'dev', '--enable-consumption', '--concurrency', '1', '--handler-timeout', '300', '--worker-id', "manual-image-$mode") `
        -RedirectStandardOutput (Join-Path $logs "$mode-$stamp.out.log") `
        -RedirectStandardError (Join-Path $logs "$mode-$stamp.err.log")
    $current += [PSCustomObject]@{ mode = $mode; id = $workerProcess.Id }
    ConvertTo-Json -InputObject @($current) | Set-Content -LiteralPath $statePath -Encoding utf8
}
Write-Output '已发起工作器启动。image、video 和 credential-test 会消费已提交的任务并可能产生供应商费用。'
Write-Output '请稍后执行 status 确认进程仍在运行；启动退出原因查看日志。'
