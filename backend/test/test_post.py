"""Tests for Post.extract_pattern — regex extraction utility."""

import pytest
from agent.post import Post


class TestExtractPattern:
    def test_extract_markdown_block(self):
        text = """```markdown
# Title
Some content here.
```"""
        result = Post.extract_pattern(text, "markdown")
        assert "# Title" in result
        assert "Some content here" in result

    def test_extract_json_block(self):
        text = '```json\n{"key": "value", "num": 42}\n```'
        result = Post.extract_pattern(text, "json")
        assert "key" in result
        assert "42" in result

    def test_extract_text_block(self):
        text = "```text\nplain content\n```"
        result = Post.extract_pattern(text, "text")
        assert "plain content" in result

    def test_extract_returns_first_match_only(self):
        text = """```markdown
first block
```
```markdown
second block
```"""
        result = Post.extract_pattern(text, "markdown")
        assert "first block" in result
        assert "second block" not in result

    def test_extract_no_match_returns_original(self):
        text = "no code blocks here"
        result = Post.extract_pattern(text, "markdown")
        assert result == text

    def test_extract_partial_match_returns_original(self):
        text = "```markdown\nunclosed block"
        result = Post.extract_pattern(text, "markdown")
        assert result == text

    def test_extract_with_newlines_and_special_chars(self):
        content = "# Title\n\n- item 1\n- item 2\n\n> quote"
        text = f"```markdown\n{content}\n```"
        result = Post.extract_pattern(text, "markdown")
        # The regex `\s` captures the trailing newline before the closing ```
        assert result.strip() == content
