#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "${PROJECT_ROOT}"

# === 可配置参数（通过环境变量覆盖）===
COMPETITION_DIR="${HERALD_COMPETITION_DIR:-${HOME}/.cache/mle-bench/data/tabular-playground-series-may-2022}"
LLM_MODEL="${HERALD_LLM_MODEL:-claude-sonnet-4-6}"
MAX_TASKS="${HERALD_MAX_TASKS:-3}"

# === 清空 workspace ===
WORKSPACE_DIR="${HERALD_WORKSPACE_DIR:-${PROJECT_ROOT}/workspace}"
if [ -d "${WORKSPACE_DIR}" ]; then
  echo "清空 workspace: ${WORKSPACE_DIR}"
  rm -rf "${WORKSPACE_DIR}"
fi

# === 加载 .env ===
if [ -f "${PROJECT_ROOT}/.env" ]; then
  set -a
  source "${PROJECT_ROOT}/.env"
  set +a
fi

# === 运行 ===
echo "竞赛: ${COMPETITION_DIR}"
echo "模型: ${LLM_MODEL}"
echo "draft 数: ${MAX_TASKS}"
echo "---"

PYTHONPATH="${PROJECT_ROOT}" conda run -n herald python core/main.py \
  --run_competition_dir "${COMPETITION_DIR}" \
  --llm_model "${LLM_MODEL}" \
  --run_max_tasks "${MAX_TASKS}"
