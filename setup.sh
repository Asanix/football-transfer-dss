#!/usr/bin/env bash
# macOS / Linux: creates .venv and installs dependencies.   bash setup.sh
set -euo pipefail
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
echo "Environment ready. Next: put the dataset in data/raw (see README) and run: bash run.sh"
