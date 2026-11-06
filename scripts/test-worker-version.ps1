# 仅在临时目录验证版本识别，不启动工作器或访问供应商。
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'worker-version.ps1')
$fixture = Join-Path ([IO.Path]::GetTempPath()) ('hf-worker-version-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path (Join-Path $fixture 'ruoyi-fastapi-backend') -Force | Out-Null
& git -C $fixture init --quiet
if ($LASTEXITCODE -ne 0) { throw '测试仓库初始化失败' }
$source = Join-Path $fixture 'ruoyi-fastapi-backend/worker.py'
$settings = Join-Path $fixture 'settings.json'
Set-Content -LiteralPath $source -Value '# 第一版'
Set-Content -LiteralPath $settings -Value '{"concurrency":2}'
$first = Get-WorkerFingerprint $fixture $settings
if ($first -ne (Get-WorkerFingerprint $fixture $settings)) { throw '相同文件指纹不稳定' }
Set-Content -LiteralPath $source -Value '# 第二版'
$second = Get-WorkerFingerprint $fixture $settings
if ($first -eq $second) { throw '未识别源码变化' }
Set-Content -LiteralPath $settings -Value '{"concurrency":4}'
$third = Get-WorkerFingerprint $fixture $settings
if ($second -eq $third) { throw '未识别配置变化' }
if ((Get-WorkerVersionDescription ([PSCustomObject]@{}) $third) -notlike '版本未知*') { throw '旧进程误判' }
if ((Get-WorkerVersionDescription ([PSCustomObject]@{fingerprint=$first}) $third) -notlike '需要重启*') { throw '过期进程误判' }
if ((Get-WorkerVersionDescription ([PSCustomObject]@{fingerprint=$third}) $third) -notlike '代码及配置一致*') { throw '当前进程误判' }
Write-Output '版本指纹测试通过：稳定性、源码变化、配置变化、未知/过期/一致三种状态。'
