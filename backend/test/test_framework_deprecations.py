"""Framework compatibility tests for public graph imports."""

import subprocess
import sys


def test_public_graphs_import_without_framework_deprecations():
    script = """
import sys
import warnings

sys.path.insert(0, "src")

from langgraph.warnings import LangGraphDeprecatedSinceV10
from pydantic.warnings import PydanticDeprecatedSince20

warnings.simplefilter("error", LangGraphDeprecatedSinceV10)
warnings.simplefilter("error", PydanticDeprecatedSince20)

import agent.configuration
import agent.graph
import agent.sub_agents.research_agent
import agent.sub_agents.writer_agent
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        cwd=".",
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
