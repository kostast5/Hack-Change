# Чат на http://127.0.0.1:8000 — из корня репозитория.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}
python -m pip install -q -r requirements.txt -r requirements-web.txt
python -m uvicorn server:app --host 127.0.0.1 --port 8000