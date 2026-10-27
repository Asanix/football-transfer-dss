#!/usr/bin/env bash
# macOS / Linux: full pipeline, then the dashboard.
#   bash run.sh                      -> Real Madrid + dashboard
#   CLUB="Real Sociedad" NOAPP=1 bash run.sh
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH=src
.venv/bin/python -m football_dss.pipeline --club "${CLUB:-Real Madrid CF}"
[ -n "${NOAPP:-}" ] || .venv/bin/python -m streamlit run app.py
