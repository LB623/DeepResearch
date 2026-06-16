#!/usr/bin/env zsh

set -e

SCRIPT_DIR="${0:A:h}"
BACKEND_DIR="${SCRIPT_DIR}/backend"
LANGGRAPH_BIN="${SCRIPT_DIR}/.venv/bin/langgraph"
PORT="${LANGGRAPH_PORT:-2024}"

if [[ ! -x "${LANGGRAPH_BIN}" ]]; then
  echo "Missing LangGraph CLI: ${LANGGRAPH_BIN}" >&2
  echo "Run: ${SCRIPT_DIR}/.venv/bin/python -m pip install -e '${BACKEND_DIR}[dev]'" >&2
  exit 1
fi

cd "${BACKEND_DIR}"
exec "${LANGGRAPH_BIN}" dev --no-browser --port "${PORT}"
