$ErrorActionPreference = 'Stop'
$appRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$dataRoot = Join-Path $appRoot '.viewer-data'
$pendingPath = Join-Path $dataRoot 'pending-update.json'
if (!(Test-Path -LiteralPath $pendingPath)) { exit 0 }
$backedUp = @(); $created = @()
try {
    $sessionPath = Join-Path $dataRoot 'session.json'
    if (Test-Path -LiteralPath $sessionPath) {
        $session = Get-Content -LiteralPath $sessionPath -Raw | ConvertFrom-Json
        $owner = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$session.pid)" -ErrorAction SilentlyContinue
        if ($owner -and $owner.ExecutablePath -and ([IO.Path]::GetFullPath($owner.ExecutablePath) -eq (Join-Path $appRoot 'runtime\python.exe'))) { exit 0 }
    }
    $pending = Get-Content -LiteralPath $pendingPath -Raw | ConvertFrom-Json
    if ($pending.version -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid pending version' }
    $payload = [IO.Path]::GetFullPath($pending.payload)
    $allowed = [IO.Path]::GetFullPath((Join-Path $dataRoot ('updates\v' + $pending.version + '\payload')))
    if ($payload -ne $allowed) { throw 'Update staging path is outside this installation' }
    $rollback = Join-Path $dataRoot ('update-rollback\' + $pending.version + '-' + [DateTime]::UtcNow.ToString('yyyyMMddHHmmssfff'))
    $rows = @()
    foreach ($file in $pending.files) {
        $rel = [string]$file.path
        if ($rel -match '(^|[\/])\.' -or $rel -match ':' -or $rel -match '^(Backups|models)[\/]' -or [IO.Path]::IsPathRooted($rel)) { throw 'Unsafe pending file path' }
        $source = [IO.Path]::GetFullPath((Join-Path $payload $rel))
        $target = [IO.Path]::GetFullPath((Join-Path $appRoot $rel))
        if (!$source.StartsWith($payload + '\', [StringComparison]::OrdinalIgnoreCase) -or !$target.StartsWith($appRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Update path escapes its root' }
         $stream = [IO.File]::OpenRead($source)
        $hasher = [Security.Cryptography.SHA256]::Create()
        try { $actualHash = [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() } finally { $stream.Dispose(); $hasher.Dispose() }
        if ($actualHash -ne $file.sha256) { throw ('Staged file changed: ' + $rel) }
        $rows += [pscustomobject]@{Source=$source;Target=$target;Relative=$rel}
    }
    foreach ($row in $rows) {
        if (Test-Path -LiteralPath $row.Target) {
            $saved = Join-Path $rollback $row.Relative
            [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($saved)) | Out-Null
            Copy-Item -LiteralPath $row.Target -Destination $saved
            $backedUp += [pscustomobject]@{Source=$saved;Target=$row.Target}
        } else { $created += $row.Target }
        [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($row.Target)) | Out-Null
        Copy-Item -LiteralPath $row.Source -Destination $row.Target -Force
    }
    Remove-Item -LiteralPath $pendingPath
    @{version=$pending.version;installed=$true;rollback=$rollback} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $dataRoot 'update-result.json') -Encoding UTF8
} catch {
    $failure = $_.Exception.Message
    foreach ($row in $backedUp) { try { Copy-Item -LiteralPath $row.Source -Destination $row.Target -Force } catch { $failure += '; rollback: ' + $_.Exception.Message } }
    foreach ($target in $created) { try { if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target } } catch { $failure += '; rollback: ' + $_.Exception.Message } }
    @{installed=$false;error=$failure} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $dataRoot 'update-result.json') -Encoding UTF8
    Write-Warning ('Update deferred; current Viewer will start. ' + $failure)
}
