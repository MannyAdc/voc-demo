"""A13: the public copy of the dashboard, for a host such as Azure App Service.

It answers only to its own host name, never reads the local staged table, never serves complaint text or the
consumer's own choice, and stores no review. Every test uses synthetic files and FastAPI's in-process test
client, so no socket is opened (A8).
"""
import importlib
import re
import shutil
import sys
import tomllib
from pathlib import Path

import pytest

from voc.labels import load_labels
from voc.load import DB_PATH, load_month

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "dbt" / "complaints.csv"
HOST = "synthetic-voc.azurewebsites.net"
HEADER = {"X-Requested-With": "voc"}


@pytest.fixture
def root(tmp_path):
    """A project with the synthetic staged table, as a careless copy might hold one."""
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    shutil.copy(REPO / "config" / "labels.toml", root / "config" / "labels.toml")
    (root / "results" / "eval").mkdir(parents=True)
    (root / "results" / "eval" / "v1_dev.csv").write_text(
        "complaint_id,split,prompt_version,proposed_label,quote_start,quote_end,decision,reason,accepted_label,"
        "tfidf_label,tfidf_confidence,recording_key\n"
        "SYN-1,dev,v1,Mortgage,10,20,accepted,,Mortgage,Mortgage,0.9," + "0" * 64 + "\n"
        "SYN-3,dev,v1,Mortgage,,,quarantined,quote_not_in_text,,Credit card,0.8," + "0" * 64 + "\n",
        encoding="utf-8")
    (root / "splits").mkdir()
    (root / "splits" / "dev.csv").write_text("complaint_id,content_hash\nSYN-1,x\nSYN-3,x\n", encoding="utf-8")
    names = [label.name for label in load_labels(root / "config" / "labels.toml")]
    load_month(root / DB_PATH, FIXTURE, "july_2026", names)
    return root


def _client(app, host=HOST):
    from fastapi.testclient import TestClient

    return TestClient(app, base_url=f"https://{host}")


def _public(root):
    from voc.api import create_app

    return create_app(root, public_host=HOST)


def test_A13_the_public_copy_answers_only_to_its_own_host(root):
    app = _public(root)
    assert _client(app).get("/api/health").status_code == 200
    for other in ("127.0.0.1", "localhost", "attacker.example"):
        assert _client(app, other).get("/api/health").status_code == 400, other


def test_A13_the_public_copy_never_serves_text_or_the_consumer_choice_even_with_the_table_there(root):
    from voc.api import create_app

    app = create_app(root, with_text=True, public_host=HOST)
    got = _client(app).get("/api/review/v1/complaint/SYN-1").json()
    assert got["text"] is None and got["consumer_choice"] is None and got["local"] is False
    listed = _client(app).get("/api/review/v1/complaints").json()
    assert listed["local"] is False and all(r["consumer_choice"] is None for r in listed["rows"])


def test_A13_the_public_copy_stores_no_review(root):
    response = _client(_public(root)).post("/api/review/v1/decision/SYN-3", headers=HEADER,
                                           json={"label": "Credit card", "reason": "word_model_right"})
    assert response.status_code == 403
    assert not (root / "results" / "reviews").exists()


def test_A13_the_public_copy_keeps_the_security_policy(root):
    response = _client(_public(root)).get("/")
    assert "default-src 'self'" in response.headers["content-security-policy"]


def test_A13_the_public_module_needs_the_host_name_from_the_platform(monkeypatch, tmp_path):
    monkeypatch.delenv("WEBSITE_HOSTNAME", raising=False)
    sys.modules.pop("voc.public", None)
    with pytest.raises(RuntimeError, match="WEBSITE_HOSTNAME"):
        importlib.import_module("voc.public")


def test_A13_the_public_module_builds_the_public_app_from_the_platform_host(monkeypatch, root):
    monkeypatch.setenv("WEBSITE_HOSTNAME", HOST)
    monkeypatch.chdir(root)
    sys.modules.pop("voc.public", None)
    public = importlib.import_module("voc.public")
    assert _client(public.app).post("/api/review/v1/decision/SYN-3", headers=HEADER,
                                    json={"label": "Credit card", "reason": "word_model_right"}).status_code == 403
    assert _client(public.app, "127.0.0.1").get("/api/health").status_code == 400
    sys.modules.pop("voc.public", None)


def test_A13_requirements_txt_pins_the_runtime_packages_only():
    lines = [line.strip() for line in (REPO / "requirements.txt").read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.startswith("#") and not line.startswith(" ")]
    names = {re.split(r"==", line)[0].lower() for line in lines}
    assert all(re.fullmatch(r"[A-Za-z0-9_.\-\[\]]+==[0-9][^ ;]*( ; .*)?", line) for line in lines), lines
    with open(REPO / "pyproject.toml", "rb") as f:
        project = tomllib.load(f)
    for dependency in project["project"]["dependencies"]:
        assert dependency.split("==")[0].lower() in names, dependency
    assert "pytest" not in names and "dbt-databricks" not in names and "voc" not in names
