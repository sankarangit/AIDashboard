$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python 3.11 or newer is required."
}
if (-not (Test-Path .venv)) {
    python -m venv .venv
}
$python = Join-Path (Get-Location) ".venv\Scripts\python.exe"
& $python -m pip install --upgrade pip
& $python -m pip install -e ".[dev]"
if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
}
New-Item -ItemType Directory -Force -Path data | Out-Null
& $python -m alembic upgrade head
& $python scripts\seed_demo.py
Write-Host "API:        http://127.0.0.1:8000"
Write-Host "Dashboard:  http://127.0.0.1:8501"
Write-Host "Starting API and Streamlit. Leave both windows open."
$root = (Get-Location).Path
Start-Process -FilePath $python -ArgumentList "-m","uvicorn","backend.main:app","--host","127.0.0.1","--port","8000" -WorkingDirectory $root
$ui = "`$env:PYTHONPATH='$root'; & '$python' -m streamlit run frontend/Home.py --server.address 127.0.0.1 --server.port 8501"
Start-Process powershell -ArgumentList "-NoExit","-Command",$ui -WorkingDirectory $root
