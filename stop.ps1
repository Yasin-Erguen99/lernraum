$ErrorActionPreference = 'Stop'
$lernraumPidFile = Join-Path $PSScriptRoot '.data\server.pid'
if (-not (Test-Path -LiteralPath $lernraumPidFile)) {
    Write-Host 'Kein Hintergrundserver registriert. Ein normales Serverfenster beendest du mit Strg+C.'
    exit 0
}
$lernraumServerId = [int](Get-Content -LiteralPath $lernraumPidFile -Raw).Trim()
$lernraumServerProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $lernraumServerId"
if ($lernraumServerProcess) {
    $lernraumExpectedScript = Join-Path $PSScriptRoot 'app.py'
    if (-not $lernraumServerProcess.CommandLine -or $lernraumServerProcess.CommandLine.IndexOf($lernraumExpectedScript, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) {
        throw 'Die Prozess-ID gehört nicht zu diesem Lernraum. Es wurde kein Prozess beendet.'
    }
    Stop-Process -Id $lernraumServerId
}
Remove-Item -LiteralPath $lernraumPidFile
Write-Host 'Lernraum beendet. Deine Daten bleiben gespeichert.'
