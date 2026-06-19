#!/usr/bin/env zsh

set -e

SCRIPT_DIR="${0:A:h}"
cd "${SCRIPT_DIR}/frontend"

if [[ ! -d node_modules ]]; then
  npm install
fi

exec npm run dev -- --host
