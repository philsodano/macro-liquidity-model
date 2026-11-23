#!/usr/bin/env bash
# Non-interactive weekly pipeline (no analyst notes). The scheduled Claude run follows RUNBOOK.md instead.
set -euo pipefail
cd "$(dirname "$0")/.."
python -m macro refresh
python -m macro build
python -m pytest -q
python -m macro report
