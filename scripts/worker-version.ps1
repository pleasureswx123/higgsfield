# 对工作器源码及配置计算内容指纹；不输出配置正文或密钥。
function Get-WorkerFingerprint([string]$Repository, [string]$SettingsPath) {
    $paths = @(& git -C $Repository ls-files --cached --others --exclude-standard -- ruoyi-fastapi-backend)
    if ($LASTEXITCODE -ne 0) { throw '无法读取工作器源码清单，不能核验版本。' }
    $paths = @($paths | Where-Object {
        ($_ -match '\.py$' -and $_ -notmatch '/tests/') -or
        $_ -match '/(pyproject\.toml|uv\.lock|requirements[^/]*\.txt)$'
    } | Sort-Object -Unique)
    $records = @()
    foreach ($path in $paths) {
        $absolute = Join-Path $Repository $path
        if (Test-Path -LiteralPath $absolute -PathType Leaf) {
            $records += $path + ':' + (Get-FileHash -LiteralPath $absolute -Algorithm SHA256).Hash
        }
    }
    foreach ($absolute in @($SettingsPath, (Join-Path $Repository 'ruoyi-fastapi-backend/.env.dev'),
        (Join-Path $Repository 'scripts/image-workers.ps1'), (Join-Path $Repository 'scripts/worker-version.ps1'))) {
        if (Test-Path -LiteralPath $absolute -PathType Leaf) {
            $records += [IO.Path]::GetFileName($absolute) + ':' + (Get-FileHash -LiteralPath $absolute -Algorithm SHA256).Hash
        }
    }
    $digest = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($digest.ComputeHash([Text.Encoding]::UTF8.GetBytes(($records -join "`n")))).Replace('-', '').ToLowerInvariant() }
    finally { $digest.Dispose() }
}

function Get-WorkerVersionDescription($Entry, [string]$CurrentFingerprint) {
    if (!$Entry.fingerprint) { return '版本未知（旧进程未记录指纹），需要重启' }
    $short = $Entry.fingerprint.Substring(0, 12)
    if ($Entry.fingerprint -eq $CurrentFingerprint) { return "代码及配置一致，指纹 $short" }
    return "需要重启，运行指纹 $short，当前指纹 $($CurrentFingerprint.Substring(0, 12))"
}
