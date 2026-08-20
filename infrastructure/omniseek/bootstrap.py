"""Create OmniSeek's local bearer credential without printing the secret."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import tempfile
from pathlib import Path

TOKEN_FILE = Path(__file__).resolve().parent / "data/credentials/omniseek_http.json"


def ensure_token(path: Path = TOKEN_FILE, *, rotate: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists() and not rotate:
        path.chmod(0o600)
        payload = json.loads(path.read_text(encoding="utf-8"))
        token = payload.get("token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or len(token) < 16:
            raise ValueError(f"invalid OmniSeek credential file: {path}")
        return path

    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=".omniseek-token-",
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump({"token": secrets.token_urlsafe(32)}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.replace(path)
        path.chmod(0o600)
    finally:
        temporary_path.unlink(missing_ok=True)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rotate",
        action="store_true",
        help="replace the current token; existing clients must reconnect",
    )
    args = parser.parse_args()
    path = ensure_token(rotate=args.rotate)
    print(f"OmniSeek credential ready: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
