# 在临时工程中模拟进程，不启动 API、数据库或供应商调用。
$ErrorActionPreference = 'Stop'
$fixtureRoot = Join-Path ([IO.Path]::GetTempPath()) ('hf-workers-test-' + [Guid]::NewGuid().ToString('N'))
$global:workerTestProcesses = @{}
$global:workerTestSpawnCount = 0
function Start-Process {
    param($FilePath, $WorkingDirectory, $WindowStyle, [switch]$PassThru, $ArgumentList, $RedirectStandardOutput, $RedirectStandardError)
    $global:workerTestSpawnCount++
    $identity = 100000 + $global:workerTestSpawnCount
    $control = $ArgumentList[[Array]::IndexOf($ArgumentList, '--control-dir') + 1].Trim('"')
    $mode = $ArgumentList[[Array]::IndexOf($ArgumentList, '--mode') + 1]
    $parallelism = $ArgumentList[[Array]::IndexOf($ArgumentList, '--concurrency') + 1]
    $global:workerTestProcesses[$identity] = [PSCustomObject]@{
        ProcessId = $identity; ExecutablePath = $FilePath; CommandLine = ($ArgumentList -join ' '); Control = $control
    }
    @{ pid = $identity; state = 'ready'; databaseReady = $true; concurrency = $parallelism; updatedAt = [DateTimeOffset]::UtcNow.ToString('o') } |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $control 'status.json') -Encoding UTF8
    return [PSCustomObject]@{ Id = $identity }
}
function Get-CimInstance {
    param($ClassName, $Filter, $ErrorAction)
    $identity = [int]($Filter -replace '\D', '')
    $process = $global:workerTestProcesses[$identity]
    if ($process -and (Test-Path -LiteralPath (Join-Path $process.Control 'stop'))) {
        $global:workerTestProcesses.Remove($identity)
        return $null
    }
    return $process
}
try {
    New-Item -ItemType Directory -Path (Join-Path $fixtureRoot 'scripts'), (Join-Path $fixtureRoot 'ruoyi-fastapi-backend/.venv/Scripts') -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot '../image-workers.ps1'), (Join-Path $PSScriptRoot '../worker-settings.json') -Destination (Join-Path $fixtureRoot 'scripts')
    New-Item -ItemType File -Path (Join-Path $fixtureRoot 'ruoyi-fastapi-backend/.venv/Scripts/python.exe') | Out-Null
    $launcher = Join-Path $fixtureRoot 'scripts/image-workers.ps1'
    & $launcher -Action start -Modes image,video -WaitSeconds 1
    & $launcher -Action start -Modes image,video -WaitSeconds 1
    if ($global:workerTestSpawnCount -ne 2) { throw '重复启动了已有进程' }
    $saved = Get-Content -LiteralPath (Join-Path $fixtureRoot 'ruoyi-fastapi-backend/output/image-workers/processes.json') -Raw | ConvertFrom-Json
    if ($saved[0].concurrency -ne 2 -or $saved[1].concurrency -ne 4) { throw '没有按模式读取并发配置' }
    & $launcher -Action status -Modes image,video
    $stateFile = Join-Path $fixtureRoot 'ruoyi-fastapi-backend/output/image-workers/processes.json'
    # 旧版清单没有控制目录：保留进程并放行，不把它误报为健康。
    $legacyEntries = @($saved | ForEach-Object { [PSCustomObject]@{ mode = $_.mode; id = $_.id } })
    ConvertTo-Json -InputObject $legacyEntries | Set-Content -LiteralPath $stateFile -Encoding UTF8
    $messages = & $launcher -Action start -Modes image,video -WaitSeconds 1 3>&1
    if ($global:workerTestSpawnCount -ne 2 -or ($messages -join '') -notmatch '无法验证就绪状态' -or ($messages -join '') -match '新版工作器健康检查通过') { throw '旧版兼容检查失败' }
    if (($messages -join '') -notmatch '-Action restart -WaitSeconds 30') { throw '缺少可复制的重启命令' }
    ConvertTo-Json -InputObject @($saved) | Set-Content -LiteralPath $stateFile -Encoding UTF8
    # 新版心跳缺失仍须报错，不能被兼容分支绕过。
    $healthPath = Join-Path $saved[0].controlDir 'status.json'
    $healthText = Get-Content -LiteralPath $healthPath -Raw
    Set-Content -LiteralPath $healthPath -Value '{}' -Encoding UTF8
    $rejected = $false
    try { & $launcher -Action start -Modes image,video -WaitSeconds 1 } catch { $rejected = $_.Exception.Message -match '尚未通过健康检查' }
    if (!$rejected) { throw '新版无心跳进程未被拒绝' }
    Set-Content -LiteralPath $healthPath -Value $healthText -Encoding UTF8
    & $launcher -Action restart -Modes image -WaitSeconds 1
    if ($global:workerTestSpawnCount -ne 3 -or $global:workerTestProcesses.Count -ne 2) { throw '按模式重启失败' }
    & $launcher -Action stop -Modes image,video -WaitSeconds 1
    if ($global:workerTestProcesses.Count -ne 0) { throw '安全停止未生效' }
    Write-Output '通过：配置读取、重复启动去重、健康状态、按模式重启、安全停止。'
} finally {
    # 只删除本测试创建的随机临时工程，绝不触碰真实工程的进程或文件。
    $resolvedFixture = [IO.Path]::GetFullPath($fixtureRoot)
    $resolvedTemp = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    if (!$resolvedFixture.StartsWith($resolvedTemp, [StringComparison]::OrdinalIgnoreCase) -or
        [IO.Path]::GetFileName($resolvedFixture) -notlike 'hf-workers-test-*') { throw '测试清理路径越界' }
    Remove-Item -LiteralPath $resolvedFixture -Recurse -Force
}
