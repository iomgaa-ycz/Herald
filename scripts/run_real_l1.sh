#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SETTINGS_FILE="${PROJECT_ROOT}/.claude/settings.local.json"

cd "${PROJECT_ROOT}"

# 清空 workspace 目录
WORKSPACE_DIR="${HERALD_WORKSPACE_DIR:-${PROJECT_ROOT}/workspace}"
if [ -d "${WORKSPACE_DIR}" ]; then
  echo "清空 workspace: ${WORKSPACE_DIR}"
  rm -rf "${WORKSPACE_DIR}"
fi

eval "$(
python - <<'PY'
import json
import shlex
from pathlib import Path

settings_path = Path(".claude/settings.local.json")
payload = json.loads(settings_path.read_text(encoding="utf-8"))
for key, value in payload.get("env", {}).items():
    print(f"export {key}={shlex.quote(str(value))}")
PY
)"

conda run -n herald python -m core.main \
  --run_competition_dir "${HOME}/.cache/mle-bench/data/tabular-playground-series-may-2022" \
  --llm_model claude-opus-4-6 \
  --run_max_tasks 1
