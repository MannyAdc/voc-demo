"""A15, review of #56: /api/health names the commit the site was built from.

The deploy writes the commit into the ZIP as BUILD_COMMIT, and the deploy's health check waits until the live
app reports that exact commit. A missing or malformed file gives null, never its content.
"""
import pytest
from fastapi.testclient import TestClient

from voc.api import create_app

SHA = "0123456789abcdef" * 2 + "01234567"


def _health(root):
    return TestClient(create_app(root), base_url="http://127.0.0.1").get("/api/health").json()


def test_A15_health_names_the_commit_in_build_commit(tmp_path):
    (tmp_path / "BUILD_COMMIT").write_text(SHA, encoding="utf-8")
    assert _health(tmp_path)["commit"] == SHA


def test_A15_health_names_no_commit_without_the_file(tmp_path):
    assert _health(tmp_path)["commit"] is None


@pytest.mark.parametrize("content", ["SYN not a commit", SHA[:39], SHA + "0", SHA.upper(), "<b>" + SHA])
def test_A15_health_names_no_commit_for_a_malformed_file(tmp_path, content):
    (tmp_path / "BUILD_COMMIT").write_text(content, encoding="utf-8")
    assert _health(tmp_path)["commit"] is None


def test_A15_a_trailing_newline_is_allowed(tmp_path):
    (tmp_path / "BUILD_COMMIT").write_text(SHA + "\n", encoding="utf-8")
    assert _health(tmp_path)["commit"] == SHA
