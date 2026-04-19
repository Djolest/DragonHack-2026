$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backendPython = Join-Path $repoRoot "backend\.venv\Scripts\python.exe"
$capturePython = Join-Path $repoRoot "capture\.venv\Scripts\python.exe"

foreach ($pythonPath in @($backendPython, $capturePython)) {
    if (-not (Test-Path $pythonPath)) {
        throw "Expected local Python environment at '$pythonPath'. Create the backend and capture .venv folders first."
    }
}

Write-Host "Starting backend on http://127.0.0.1:8000" -ForegroundColor Cyan
$backendJob = Start-Job -Name "oakproof-backend" -ScriptBlock {
    param($workingDir, $pythonPath)
    Set-Location $workingDir
    & $pythonPath -m uvicorn app.main:app --host 127.0.0.1 --port 8000
} -ArgumentList (Join-Path $repoRoot "backend"), $backendPython

Write-Host "Starting capture station on http://127.0.0.1:8100" -ForegroundColor Cyan
$captureJob = Start-Job -Name "oakproof-capture" -ScriptBlock {
    param($workingDir, $pythonPath)
    Set-Location $workingDir
    & $pythonPath -m uvicorn app.main:app --host 127.0.0.1 --port 8100
} -ArgumentList (Join-Path $repoRoot "capture"), $capturePython

Write-Host "Starting verifier on http://127.0.0.1:5173" -ForegroundColor Cyan

try {
    Set-Location $repoRoot
    npm run dev --workspace verifier -- --host 127.0.0.1 --port 5173
}
finally {
    foreach ($job in @($captureJob, $backendJob)) {
        if ($null -ne $job) {
            Stop-Job -Job $job -ErrorAction SilentlyContinue | Out-Null
            Remove-Job -Job $job -Force -ErrorAction SilentlyContinue | Out-Null
        }
    }
}
