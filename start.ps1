param([switch]$Background, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
try {
    $existingLernraum = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/health' -TimeoutSec 2
    if ($existingLernraum.app -eq 'Lernraum' -and $existingLernraum.ok) {
        Write-Host 'Lernraum läuft bereits: http://127.0.0.1:8765'
        if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:8765' }
        exit 0
    }
} catch {
    # No existing local server; start it below.
}
$bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$lernraumPythonArgs = @('-B', '-u')
if (Test-Path -LiteralPath $bundledPython) {
    $lernraumPython = $bundledPython
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $lernraumPython = (Get-Command python).Source
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $lernraumPython = (Get-Command py).Source
    $lernraumPythonArgs = @('-3', '-B', '-u')
} else {
    Write-Host 'Python 3.12 oder neuer wird benötigt. Installiere Python und starte erneut.'
    Read-Host 'Enter zum Schließen'
    exit 1
}
$lernraumScript = Join-Path $PSScriptRoot 'app.py'
if ($Background) {
    $lernraumData = Join-Path $PSScriptRoot '.data'
    New-Item -ItemType Directory -Path $lernraumData -Force | Out-Null
    $lernraumArguments = $lernraumPythonArgs + @(('"{0}"' -f $lernraumScript))
    $lernraumProcess = Start-Process -FilePath $lernraumPython -ArgumentList $lernraumArguments -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $lernraumData 'server.log') -RedirectStandardError (Join-Path $lernraumData 'server-error.log') -PassThru
    $lernraumReady = $false
    for ($attempt = 0; $attempt -lt 12; $attempt++) {
        if ($lernraumProcess.HasExited) { break }
        try {
            $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/health' -TimeoutSec 1
            if ($health.ok -and $health.app -eq 'Lernraum') { $lernraumReady = $true; break }
        } catch { Start-Sleep -Milliseconds 200 }
    }
    if (-not $lernraumReady) { throw 'Lernraum konnte nicht gestartet werden. Siehe .data/server-error.log.' }
    Set-Content -LiteralPath (Join-Path $lernraumData 'server.pid') -Value $lernraumProcess.Id -Encoding ascii
    Write-Host 'Lernraum läuft: http://127.0.0.1:8765'
    if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:8765' }
} else {
    if ($NoBrowser) { & $lernraumPython @lernraumPythonArgs $lernraumScript }
    else { & $lernraumPython @lernraumPythonArgs $lernraumScript --open }
    exit $LASTEXITCODE
}
