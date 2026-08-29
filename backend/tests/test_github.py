"""Tests for GitHub repo-URL parsing (plan Phase 2).

Pure regex logic — no network. Guards the many shapes a user may paste into the
"Add repository" form.
"""
from __future__ import annotations

import pytest

from app.github.client import parse_repo_url


@pytest.mark.parametrize(
    "raw",
    [
        "https://github.com/octocat/Hello-World",
        "https://github.com/octocat/Hello-World.git",
        "https://github.com/octocat/Hello-World/",
        "http://github.com/octocat/Hello-World",
        "git@github.com:octocat/Hello-World.git",
        "octocat/Hello-World",
        "  octocat/Hello-World  ",
    ],
)
def test_parse_repo_url_accepts_common_shapes(raw):
    ref = parse_repo_url(raw)
    assert ref.owner == "octocat"
    assert ref.repo == "Hello-World"
    assert ref.full_name == "octocat/Hello-World"


@pytest.mark.parametrize("raw", ["", "not-a-repo", "https://github.com/only-owner"])
def test_parse_repo_url_rejects_garbage(raw):
    with pytest.raises(ValueError):
        parse_repo_url(raw)
