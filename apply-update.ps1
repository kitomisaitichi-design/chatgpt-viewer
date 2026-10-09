$ErrorActionPreference = 'Stop'
$appRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$dataRoot = Join-Path $appRoot '.viewer-data'
$pendingPath = Join-Path $dataRoot 'pending-update.json'
$transactionPath = Join-Path $dataRoot 'update-transaction.json'
$resultPath = Join-Path $dataRoot 'update-result.json'

function Check-Relative([string]$relative) {
    if (!$relative -or $relative -match '(^|[\/])\.' -or $relative -match ':' -or
        $relative -match '^(Backups|models)[\/]' -or [IO.Path]::IsPathRooted($relative)) {
        throw ('Unsafe update file path: ' + $relative)
    }
}
function Within([string]$root, [string]$path) {
    $full = [IO.Path]::GetFullPath($path)
    if (!$full.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw ('Update path escapes its root: ' + $full)
    }
    return $full
}
function Hash-File([string]$path) {
    return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Restore-Transaction($journal) {
    if ($journal.version -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid recovery version' }
    $rollbackRoot = [IO.Path]::GetFullPath([string]$journal.rollback)
    $rollbacks = [IO.Path]::GetFullPath((Join-Path $dataRoot 'update-rollback'))
    $rollbackRoot = Within $rollbacks $rollbackRoot
    $actions = @()
    # Validate all old copies before replacing *any* live files.
    foreach ($entry in $journal.files) {
        $relative = [string]$entry.path
        Check-Relative $relative
        $target = Within $appRoot (Join-Path $appRoot $relative)
        if ($entry.existed -eq $true) {
            $source = Within $rollbackRoot (Join-Path $rollbackRoot $relative)
            if (!(Test-Path -LiteralPath $source -PathType Leaf) -or (Hash-File $source) -ne [string]$entry.previous_sha256) {
                throw ('Missing or damaged update recovery copy: ' + $relative)
            }
            $actions += [pscustomobject]@{Source=$source;Target=$target;Existed=$true}
        } else {
            $actions += [pscustomobject]@{Source='';Target=$target;Existed=$false}
        }
    }
    foreach ($entry in $actions) {
        if ($entry.Existed) {
            [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($entry.Target)) | Out-Null
            Copy-Item -LiteralPath $entry.Source -Destination $entry.Target -Force
        } elseif (Test-Path -LiteralPath $entry.Target) {
            Remove-Item -LiteralPath $entry.Target -Force
        }
    }
}

# Recovery happens even if a previous run removed pending-update.json before
# being killed. The preinstall journal and all original bytes are durable.
try {
    # Preserve the original live-process guard for both rollback recovery and
    # installation; never rewrite a release while its bundled viewer is active.
    $sessionPath = Join-Path $dataRoot 'session.json'
    if (Test-Path -LiteralPath $sessionPath) {
        $session = Get-Content -LiteralPath $sessionPath -Raw | ConvertFrom-Json
        $owner = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$session.pid)" -ErrorAction SilentlyContinue
        if ($owner -and $owner.ExecutablePath -and ([IO.Path]::GetFullPath($owner.ExecutablePath) -eq (Join-Path $appRoot 'runtime\python.exe'))) { exit 0 }
    }
    if (Test-Path -LiteralPath $transactionPath) {
        $journal = Get-Content -LiteralPath $transactionPath -Raw | ConvertFrom-Json
        if ($journal.version -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid recovery version' }
        $complete = !(Test-Path -LiteralPath $pendingPath)
        if ($complete) {
            foreach ($entry in $journal.files) {
                Check-Relative ([string]$entry.path)
                $target = Within $appRoot (Join-Path $appRoot ([string]$entry.path))
                if (!(Test-Path -LiteralPath $target -PathType Leaf) -or (Hash-File $target) -ne [string]$entry.sha256) {
                    $complete = $false
                    break
                }
            }
        }
        if ($complete) {
            Remove-Item -LiteralPath $transactionPath -Force
            @{version=$journal.version;installed=$true;rollback=$journal.rollback;recovered='verified-complete'} | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8
            exit 0
        }
        Restore-Transaction $journal
        Remove-Item -LiteralPath $transactionPath -Force
        if (!(Test-Path -LiteralPath $pendingPath)) {
            @{installed=$false;recovered='restored-original';error='Interrupted update was rolled back.'} | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8
            exit 0
        }
    }
} catch {
    @{installed=$false;error=('Update recovery failed: ' + $_.Exception.Message)} | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8
    Write-Warning ('Update recovery needs attention: ' + $_.Exception.Message)
    exit 2
}

if (!(Test-Path -LiteralPath $pendingPath)) { exit 0 }
try {
    $pending = Get-Content -LiteralPath $pendingPath -Raw | ConvertFrom-Json
    if ($pending.version -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid pending version' }
    $payload = [IO.Path]::GetFullPath($pending.payload)
    $allowed = [IO.Path]::GetFullPath((Join-Path $dataRoot ('updates\v' + $pending.version + '\payload')))
    if ($payload -ne $allowed) { throw 'Update staging path is outside this installation' }
    $rollback = Join-Path $dataRoot ('update-rollback\' + $pending.version + '-' + [DateTime]::UtcNow.ToString('yyyyMMddHHmmssfff'))
    $rows = @()
    foreach ($file in $pending.files) {
        $rel = [string]$file.path
        Check-Relative $rel
        $source = Within $payload (Join-Path $payload $rel)
        $target = Within $appRoot (Join-Path $appRoot $rel)
        if ((Hash-File $source) -ne $file.sha256) { throw ('Staged file changed: ' + $rel) }
        $rows += [pscustomobject]@{Source=$source;Target=$target;Relative=$rel;Hash=$file.sha256}
    }
    # Copy *all* original files before changing the first live byte.
    $journalFiles = @()
    foreach ($row in $rows) {
        $existed = Test-Path -LiteralPath $row.Target -PathType Leaf
        $oldHash = ''
        if ($existed) {
            $saved = Join-Path $rollback $row.Relative
            [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($saved)) | Out-Null
            $oldHash = Hash-File $row.Target
            Copy-Item -LiteralPath $row.Target -Destination $saved
            if ((Hash-File $saved) -ne $oldHash) { throw ('Update backup changed during copy: ' + $row.Relative) }
        }
        $journalFiles += @{path=$row.Relative;existed=[bool]$existed;previous_sha256=$oldHash;sha256=$row.Hash}
    }
    # Atomic publication ensures a crash can only occur before or after the
    # recovery journal is present; the update starts strictly after this step.
    $journal = @{version=$pending.version;rollback=$rollback;files=$journalFiles}
    $temporaryJournal = $transactionPath + '.partial'
    [IO.File]::WriteAllText($temporaryJournal,($journal | ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporaryJournal -Destination $transactionPath -Force
    foreach ($row in $rows) {
        [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($row.Target)) | Out-Null
        Copy-Item -LiteralPath $row.Source -Destination $row.Target -Force
        if ((Hash-File $row.Target) -ne $row.Hash) { throw ('Installed file failed verification: ' + $row.Relative) }
    }
    Remove-Item -LiteralPath $pendingPath
    Remove-Item -LiteralPath $transactionPath
    @{version=$pending.version;installed=$true;rollback=$rollback} | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8
} catch {
    $failure = $_.Exception.Message
    if (Test-Path -LiteralPath $transactionPath) {
        try {
            $journal = Get-Content -LiteralPath $transactionPath -Raw | ConvertFrom-Json
            Restore-Transaction $journal
            Remove-Item -LiteralPath $transactionPath -Force
        } catch { $failure += '; rollback: ' + $_.Exception.Message }
    }
    @{installed=$false;error=$failure} | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8
    Write-Warning ('Update deferred; current Viewer will start. ' + $failure)
}
