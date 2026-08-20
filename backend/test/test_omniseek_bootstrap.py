"""Tests for secure OmniSeek host credential bootstrap."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path


def _bootstrap_module():
    script = (
        Path(__file__).resolve().parents[2]
        / "infrastructure"
        / "omniseek"
        / "bootstrap.py"
    )
    spec = importlib.util.spec_from_file_location("omniseek_bootstrap", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bootstrap_is_idempotent_and_never_weakens_permissions(tmp_path):
    module = _bootstrap_module()
    token_file = tmp_path / "credentials" / "omniseek_http.json"

    module.ensure_token(token_file)
    first = json.loads(token_file.read_text(encoding="utf-8"))["token"]
    module.ensure_token(token_file)
    second = json.loads(token_file.read_text(encoding="utf-8"))["token"]

    assert first == second
    assert len(first) >= 16
    if os.name == "posix":
        assert token_file.stat().st_mode & 0o077 == 0


def test_bootstrap_rotation_replaces_the_token(tmp_path):
    module = _bootstrap_module()
    token_file = tmp_path / "credentials" / "omniseek_http.json"

    module.ensure_token(token_file)
    first = token_file.read_text(encoding="utf-8")
    module.ensure_token(token_file, rotate=True)

    assert token_file.read_text(encoding="utf-8") != first
