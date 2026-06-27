# TrustShield — one-command local launcher (Windows).
#
# Starts all three services from the local venv so the learned-model "deep scan" runs on your GPU:
#   forensics  http://localhost:8001   (PyTorch + CUDA → deep scan enabled)
#   risk       http://localhost:8002
#   dashboard  http://localhost:5173   (opens in your browser)
#
# Run:  .\start.ps1        (or double-click start.bat)
# Stop: close the three windows, or run  .\stop.ps1

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$py   = Join-Path $root ".venv\Scripts\python.exe"
$dash = Join-Path $root "services\dashboard"

if (-not (Test-Path $py)) {
    Write-Host "[x] Python venv not found at $py" -ForegroundColor Red
    Write-Host "    Create it once, then re-run this script:" -ForegroundColor Yellow
    Write-Host "      python -m venv .venv"
    Write-Host "      .\.venv\Scripts\python -m pip install -r services\forensics\requirements.txt -r services\risk\requirements.txt -r data\generator\requirements.txt"
    Write-Host "      .\.venv\Scripts\python -m pip install -r services\forensics\requirements-models.txt   # torch (GPU deep scan)"
    exit 1
}

$env:PYTHONPATH = $root
$env:PYTHONUNBUFFERED = "1"

# Synthetic packets are not committed — regenerate them on first run if missing.
if (-not (Test-Path (Join-Path $root "data\synthetic\labels.json"))) {
    Write-Host "Generating synthetic loan packets (first run)..." -ForegroundColor Yellow
    & $py -m data.generator.generate
}

# Is the GPU deep-scan model ready (torch + weights present)?
$deep = & $py -c "import sys; sys.path.insert(0, r'$root'); from services.forensics.app.ingest import forgery_model as m; print('yes' if m.available('unet') else 'no')" 2>$null
$gpu  = & $py -c "import torch; print('GPU' if torch.cuda.is_available() else 'CPU')" 2>$null

Write-Host "Starting TrustShield (local)..." -ForegroundColor Cyan
Write-Host ("  deep scan (learned model): {0}   compute: {1}" -f $deep, $gpu) -ForegroundColor DarkCyan

# Backends — each opens its own console window so you can watch the logs.
Start-Process -FilePath $py -WorkingDirectory $root `
    -ArgumentList '-m','uvicorn','services.forensics.app.main:app','--host','127.0.0.1','--port','8001'
Start-Process -FilePath $py -WorkingDirectory $root `
    -ArgumentList '-m','uvicorn','services.risk.app.main:app','--host','127.0.0.1','--port','8002'

# Dashboard — install deps on first run, then start Vite.
if (-not (Test-Path (Join-Path $dash "node_modules"))) {
    Write-Host "Installing dashboard dependencies (first run only)..." -ForegroundColor Yellow
    Push-Location $dash; npm install; Pop-Location
}
Start-Process -FilePath 'cmd.exe' -WorkingDirectory $dash -ArgumentList '/k','npm run dev'

function Wait-Health($url, $name) {
    for ($i = 0; $i -lt 40; $i++) {
        try {
            if ((Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 $url).StatusCode -eq 200) {
                Write-Host ("  [ok] {0}" -f $name) -ForegroundColor Green; return
            }
        } catch { }
        Start-Sleep -Milliseconds 750
    }
    Write-Host ("  [..] {0} not up yet (check its window)" -f $name) -ForegroundColor Yellow
}

Write-Host "Waiting for services..." -ForegroundColor Cyan
Wait-Health "http://127.0.0.1:8001/health" "forensics :8001"
Wait-Health "http://127.0.0.1:8002/health" "risk :8002"
Start-Sleep -Seconds 2          # give Vite a moment to bind
Start-Process "http://localhost:5173"

Write-Host ""
Write-Host "TrustShield is running:" -ForegroundColor Green
Write-Host "  Dashboard  http://localhost:5173"
Write-Host "  Forensics  http://localhost:8001/health"
Write-Host "  Risk       http://localhost:8002/health"
Write-Host ""
Write-Host "Single-document tip: upload runs the zero-false-positive heuristics first." -ForegroundColor DarkGray
Write-Host "On a CLEAN result, click 'Run learned model (deep scan)' to catch seamless edits (GPU)." -ForegroundColor DarkGray
Write-Host "Stop everything by closing the windows, or run  .\stop.ps1" -ForegroundColor DarkGray
