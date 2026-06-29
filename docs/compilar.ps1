# =====================================================================
# TeleFlow Platform — Script de compilación de documentación Typst
# =====================================================================
# Uso:
#   cd docs
#   .\compilar.ps1
#
# Requisitos:
#   Typst >= 0.11 instalado. Si no está:
#     winget install --id Typst.Typst
#   O descargarlo de: https://github.com/typst/typst/releases
# =====================================================================

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Verificar que typst esté disponible
if (-not (Get-Command typst -ErrorAction SilentlyContinue)) {
    Write-Host "Typst no encontrado. Instalando via winget..." -ForegroundColor Yellow
    winget install --id Typst.Typst --silent
    # Refrescar PATH
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("PATH", "User")
}

$MainFile = Join-Path $ScriptDir "main.typ"
$OutFile  = Join-Path $ScriptDir "TeleFlow-Platform-Docs-v1.0.pdf"

Write-Host "Compilando documentación TeleFlow..." -ForegroundColor Cyan
Write-Host "  Entrada: $MainFile"
Write-Host "  Salida:  $OutFile"

typst compile $MainFile $OutFile

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✓ PDF generado: TeleFlow-Platform-Docs-v1.0.pdf" -ForegroundColor Green
    Write-Host ""
    Write-Host "Para abrir:" -ForegroundColor Gray
    Write-Host "  Start-Process '$OutFile'" -ForegroundColor Gray
} else {
    Write-Host "✗ Error al compilar. Verificar mensajes de Typst arriba." -ForegroundColor Red
    exit 1
}
