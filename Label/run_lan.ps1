param(
    [string]$Input = "artifacts/splits/core.csv",
    [string]$Subset = "core-1000",
    [int]$Port = 8765
)

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

Write-Host "ViRPM annotation app is starting on the local network..." -ForegroundColor Cyan
Write-Host "Find this computer's IPv4 address with: ipconfig" -ForegroundColor Yellow
Write-Host "Give annotators: http://<IPv4>:$Port" -ForegroundColor Yellow
python Label/app.py --input $Input --subset $Subset --host 0.0.0.0 --port $Port
