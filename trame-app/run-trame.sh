#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYTHON="$SCRIPT_DIR/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
    echo "venv not found — run ./setup-trame.sh first" >&2
    exit 1
fi

exec "$PYTHON" "$SCRIPT_DIR/app.py" "$@"
