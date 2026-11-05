param(
    [ValidateSet('start', 'status', 'stop', 'restart')]
    [string]$Action = 'status',
    [ValidateSet('image', 'image-recovery', 'video', 'archive', 'billing', 'image-thumbnail', 'credential-test')]
    [string[]]$Modes = @('image', 'image-recovery', 'video', 'archive', 'billing', 'image-thumbnail', 'credential-test'),
    [string]$ConfigPath = (Join-Path $PSScriptRoot 'worker-settings.json'),
    [ValidateRange(1, 3600)][int]$WaitSeconds = 30
)
$ErrorActionPreference = 'Stop'
$backend = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../ruoyi-fastapi-backend'))
$python = Join-Path $backend '.venv/Scripts/python.exe'
$logs = Join-Path $backend 'output/image-workers'
$statePath = Join-Path $logs 'processes.json'
$config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($mode in $Modes) {
    $setting = $config.modes.$mode
    if (!$setting -or $setting.concurrency -lt 1 -or $setting.concurrency -gt 100 -or
        $setting.concurrency -ne [int]$setting.concurrency -or
        $setting.handlerTimeout -lt 1 -or $setting.handlerTimeout -gt 3600) { throw "工作器配置无效：$mode" }
}
if ($config.drainSeconds -lt 1 -or $config.drainSeconds -gt 3600) { throw '安全停机期限须为1到3600秒' }

function Get-OwnedWorker($entry) {
    $candidate = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$entry.id)" -ErrorAction SilentlyContinue
    if ($candidate -and $candidate.ExecutablePath -eq $python -and
        $candidate.CommandLine -like '*module_higgsfield.worker*' -and
        $candidate.CommandLine -match "--mode $([regex]::Escape($entry.mode))( |$)" -and
        $candidate.CommandLine -like '*--worker-id manual-image-*') { return $candidate }
    return $null
}
function Get-Health($entry) {
    if (!$entry.controlDir) { return $null }
    $file = Join-Path $entry.controlDir 'status.json'
    if (!(Test-Path -LiteralPath $file)) { return $null }
    try { return Get-Content -LiteralPath $file -Raw -Encoding UTF8 | ConvertFrom-Json } catch { return $null }
}
function Test-Ready($entry) {
    $health = Get-Health $entry
    return ($health -and $health.state -eq 'ready' -and $health.databaseReady -and
        ([DateTimeOffset]::UtcNow - [DateTimeOffset]::Parse($health.updatedAt)).TotalSeconds -lt 10)
}
# 同一工程的启动操作串行化，避免两个终端重复启动。
$sha = [System.Security.Cryptography.SHA256]::Create()
$hash = [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($backend))).Replace('-', '')
$sha.Dispose()
$mutex = New-Object Threading.Mutex($false, "Local\HiggsfieldWorkers-$hash")
$locked = $false
try {
    try { $locked = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $locked = $true }
    if (!$locked) { throw '另一个终端正在管理工作器，请稍后重试。' }
    $saved = @()
    if (Test-Path -LiteralPath $statePath) { $saved = ConvertFrom-Json -InputObject (Get-Content -LiteralPath $statePath -Raw -Encoding UTF8) }
    if ($Action -eq 'status') {
        foreach ($mode in $Modes) {
            $entry = $saved | Where-Object { $_.mode -eq $mode } | Select-Object -First 1
            if (!$entry -or !(Get-OwnedWorker $entry)) { Write-Output "$mode : 未运行"; continue }
            $health = Get-Health $entry
            $description = if (Test-Ready $entry) { '新版（支持健康心跳），就绪，数据库连接正常' } elseif (!$entry.controlDir) { '旧版（无健康心跳），无法验证就绪状态' } elseif ($health) { "新版，状态 $($health.state)，请检查心跳时间 $($health.updatedAt)" } else { '新版，初始化中或心跳缺失' }
            Write-Output "$mode : PID $($entry.id)，$description，配置并发/批量 $($entry.concurrency)"
        }
        Write-Output "日志目录：$logs"
        return
    }
    if ($Action -in @('stop', 'restart')) {
        foreach ($entry in $saved) {
            if ($entry.mode -notin $Modes -or !(Get-OwnedWorker $entry)) { continue }
            if (!$entry.controlDir) { throw "旧版工作器 $($entry.mode) 不支持安全停止，请在没有在途任务时手动停止旧进程，再使用本脚本启动。" }
            Set-Content -LiteralPath (Join-Path $entry.controlDir 'stop') -Value 'stop' -Encoding UTF8
        }
        $deadline = [DateTime]::UtcNow.AddSeconds($WaitSeconds)
        do {
            $remaining = @($saved | Where-Object { $_.mode -in $Modes -and (Get-OwnedWorker $_) })
            if (!$remaining.Count) { break }
            Start-Sleep -Milliseconds 250
        } while ([DateTime]::UtcNow -lt $deadline)
        if ($remaining.Count) { throw "已请求安全停止，仍在等待在途任务：$($remaining.mode -join ', ')。未强杀或启动重复进程；稍后查看 status。" }
        Write-Output '工作器已停止。'
        if ($Action -eq 'stop') { return }
    }
    if (!(Test-Path -LiteralPath $python)) { throw '未找到后端虚拟环境。' }
    New-Item -ItemType Directory -Path $logs -Force | Out-Null
    $current = @($saved | Where-Object { $_.mode -notin $Modes })
    foreach ($mode in $Modes) {
        $entry = $saved | Where-Object { $_.mode -eq $mode } | Select-Object -First 1
        if ($entry -and (Get-OwnedWorker $entry)) {
            $current += $entry
            $generation = if ($entry.controlDir) { '新版（支持健康心跳）' } else { '旧版（无健康心跳）' }
            Write-Output "$mode : $generation，PID $($entry.id)，复用现有进程。"
            continue
        }
        $setting = $config.modes.$mode
        $stamp = [Guid]::NewGuid().ToString('N')
        $control = Join-Path $logs "$mode-$stamp"
        New-Item -ItemType Directory -Path $control -Force | Out-Null
        $workerProcess = Start-Process -FilePath $python -WorkingDirectory $backend -WindowStyle Hidden -PassThru `
            -ArgumentList @('-m', 'module_higgsfield.worker', '--mode', $mode, '--env', 'dev', '--enable-consumption', '--concurrency', $setting.concurrency, '--handler-timeout', $setting.handlerTimeout, '--drain-seconds', $config.drainSeconds, '--control-dir', ('"' + $control + '"'), '--worker-id', "manual-image-$mode-$stamp") `
            -RedirectStandardOutput (Join-Path $control 'out.log') -RedirectStandardError (Join-Path $control 'err.log')
        $current += [PSCustomObject]@{ mode = $mode; id = $workerProcess.Id; controlDir = $control; concurrency = $setting.concurrency }
        ConvertTo-Json -InputObject @($current) | Set-Content -LiteralPath $statePath -Encoding UTF8
    }
    $legacy = @($current | Where-Object { $_.mode -in $Modes -and !$_.controlDir -and (Get-OwnedWorker $_) })
    if ($legacy.Count) {
        Write-Warning "保留旧版工作器：$($legacy.mode -join ', ')。这些进程没有健康心跳，无法验证就绪状态；不阻止 API 启动。新版调度能力需在无在途任务时切换到新工作器。"
    }
    $deadline = [DateTime]::UtcNow.AddSeconds($WaitSeconds)
    do {
        $waiting = @($current | Where-Object { $_.mode -in $Modes -and (!(Get-OwnedWorker $_) -or ($_.controlDir -and !(Test-Ready $_))) })
        if (!$waiting.Count) { break }
        if (@($waiting | Where-Object { !(Get-OwnedWorker $_) }).Count) { break }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    if ($waiting.Count) { throw "工作器尚未通过健康检查：$($waiting.mode -join ', ')。查看 $logs；未重复启动现有进程。" }
    $verified = @($current | Where-Object { $_.mode -in $Modes -and $_.controlDir } | ForEach-Object { $_.mode })
    if ($verified.Count) { Write-Output "新版工作器健康检查通过：$($verified -join ', ')。并发/批量配置：$ConfigPath" }
    Write-Output '日常启动无需重启工作器；修改工作器代码或配置后，在另一个 PowerShell 窗口执行：'
    Write-Output ('& "' + $PSCommandPath + '" -Action restart -WaitSeconds 30')
    Write-Output '重启会先停止领取，再等待在途任务；若超过30秒仍未退出，请稍后查看 status，停止完成后再执行 start。'
    Write-Output '工作器会处理已有待执行任务，可能调用收费供应商；就绪不代表供应商生成成功。'
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
