#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "=== Doc-Studio Portable Installer (macOS/Linux) ==="

if command -v uv >/dev/null 2>&1; then
  uv venv .venv
  uv pip install --python .venv/bin/python -e .
else
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -e .
fi

(cd "$ROOT/layout" && npm install)
npm install -g repomix @drawio/mcp

.venv/bin/python scripts/bootstrap_assets.py
.venv/bin/python engine/cli.py doctor

echo "Done! Link this folder into ~/.gemini/config/plugins/doc-studio for Antigravity, or import mcp_config.json into Claude Code / Cursor / Codex."
