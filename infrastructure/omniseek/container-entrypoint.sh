#!/bin/sh
# Silent first-boot fallback. The host bootstrap normally creates this file first,
# but direct Compose users must not leak a newly generated bearer token to logs.
set -eu

OMNISEEK_STATE_DIR="${HOME:-/root}/.omniseek"
OMNISEEK_TOKEN_PATH="${OMNISEEK_STATE_DIR}/credentials/omniseek_http.json"

if [ ! -f "${OMNISEEK_TOKEN_PATH}" ]; then
    umask 077
    mkdir -p "${OMNISEEK_STATE_DIR}/credentials"
    python - "${OMNISEEK_TOKEN_PATH}" <<'PY'
import json
import pathlib
import secrets
import sys

path = pathlib.Path(sys.argv[1])
path.write_text(json.dumps({"token": secrets.token_urlsafe(32)}), encoding="utf-8")
path.chmod(0o600)
PY
fi

exec /usr/local/bin/docker-entrypoint.sh "$@"
