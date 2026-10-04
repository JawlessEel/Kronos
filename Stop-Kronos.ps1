$ErrorActionPreference = 'Stop'
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$listeners = @(Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 7070 -State Listen -ErrorAction SilentlyContinue)
foreach ($listener in $listeners) {
    $serverProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
    # Windows venv launchers may run the base interpreter as a child process.
    $parentProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($serverProcess.ParentProcessId)"
    $isProjectPython = $serverProcess.ExecutablePath -eq $pythonPath -or $parentProcess.ExecutablePath -eq $pythonPath
    if (-not $isProjectPython -or $serverProcess.CommandLine -notmatch 'scripts[\\/]run_webui\.py') {
        throw 'Port 7070 belongs to another application; refusing to stop it.'
    }
    Stop-Process -Id $serverProcess.ProcessId
    Write-Output 'Kronos stopped.'
}
if ($listeners.Count -eq 0) { Write-Output 'Kronos is already stopped.' }
