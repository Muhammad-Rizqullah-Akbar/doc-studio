$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "=== Doc-Studio Portable Installer (Windows) ===" -ForegroundColor Cyan

# 1. Python venv setup (uv preferred, fallback python -m venv)
if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv venv .venv
    uv pip install --python .venv\Scripts\python.exe -e .
} else {
    python -m venv .venv
    .venv\Scripts\python.exe -m pip install --upgrade pip
    .venv\Scripts\python.exe -m pip install -e .
}

# 2. Node ELK layout engine + global MCP servers
Push-Location (Join-Path $Root "layout")
npm install
Pop-Location
npm install -g repomix @drawio/mcp

# 3. Download free binaries, KBBI dataset, LibreOffice id_ID, CSL styles, Vale packages, and generate mcp_config.json
.venv\Scripts\python.exe scripts\bootstrap_assets.py

# 4. Run health check
.venv\Scripts\python.exe engine\cli.py doctor
Write-Host "`nDone! Copy or link this folder into ~/.gemini/config/plugins/doc-studio for Antigravity, or import mcp_config.json into Claude Code / Cursor / Codex." -ForegroundColor Green
