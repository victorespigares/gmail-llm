#!/usr/bin/env bash
# gmail_export.sh — Run gmail_export.py inside its own venv.
#
# Usage:
#   ./gmail_export.sh "GMAIL_QUERY" [options]
#
# Examples:
#   ./gmail_export.sh "label:inbox after:2024/01/01"
#   ./gmail_export.sh "from:boss@company.com" --max-results 100 --format txt
#   ./gmail_export.sh "subject:invoice" --format both --output-file invoices
#
# All options are forwarded to gmail_export.py (see --help).
# Output files are always written to ./output/ (next to this script).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python"
PYTHON_SCRIPT="$SCRIPT_DIR/gmail_export.py"
OUTPUT_DIR="$SCRIPT_DIR/output"

# ── Sanity checks ─────────────────────────────────────────────────────────────

if [[ $# -eq 0 ]]; then
    echo "Usage: $(basename "$0") \"GMAIL_QUERY\" [options]"
    echo "       $(basename "$0") --help"
    exit 1
fi

if [[ ! -f "$VENV_PYTHON" ]]; then
    echo "Error: virtual environment not found at $SCRIPT_DIR/venv"
    echo "Run: python3 -m venv venv && venv/bin/pip install -r requirements.txt"
    exit 1
fi

if [[ ! -f "$PYTHON_SCRIPT" ]]; then
    echo "Error: gmail_export.py not found at $PYTHON_SCRIPT"
    exit 1
fi

# ── Ensure output directory exists ───────────────────────────────────────────

mkdir -p "$OUTPUT_DIR"

# ── Activate venv and run ─────────────────────────────────────────────────────

source "$SCRIPT_DIR/venv/bin/activate"

exec "$VENV_PYTHON" "$PYTHON_SCRIPT" --output-dir "$OUTPUT_DIR" "$@"
