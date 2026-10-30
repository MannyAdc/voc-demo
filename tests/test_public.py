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
    # Changed in the green commit of the review of #50: the module is removed in `finally`, so a failure here
    # cannot leave it cached for other tests.
    monkeypatch.setenv("WEBSITE_HOSTNAME", HOST)
    monkeypatch.chdir(root)
    sys.modules.pop("voc.public", None)
    try:
        public = importlib.import_module("voc.public")
        assert _client(public.app).post("/api/review/v1/decision/SYN-3", headers=HEADER,
                                        json={"label": "Credit card", "reason": "word_model_right"}).status_code == 403
        assert _client(public.app, "127.0.0.1").get("/api/health").status_code == 400
    finally:
        sys.modules.pop("voc.public", None)


def test_A13_requirements_txt_lines_are_pinned():
    # Changed in the green commit of the review of #50: requirements.txt now holds the public copy's packages
    # only, so it no longer pins every project dependency. What it must hold is checked below, against uv.lock.
    lines = [line.strip() for line in (REPO / "requirements.txt").read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.startswith("#") and not line.startswith(" ")]
    assert lines and all(re.fullmatch(r"[A-Za-z0-9_.\-\[\]]+==[0-9][^ ;]*( ; .*)?", line) for line in lines), lines


# Review of #50


def _locked_versions():
    with open(REPO / "uv.lock", "rb") as f:
        return {p["name"].lower(): p["version"] for p in tomllib.load(f)["package"] if "version" in p}


def _pins():
    lines = [line.strip() for line in (REPO / "requirements.txt").read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.startswith("#") and not line.startswith(" ")]
    return {line.split("==")[0].lower(): line.split("==")[1].split(" ")[0] for line in lines}


def test_A13_requirements_txt_pins_only_what_the_public_copy_needs_at_the_locked_versions():
    pins, locked = _pins(), _locked_versions()
    assert pins and all(locked.get(name) == version for name, version in pins.items()), pins
    for heavy in ("dbt-core", "scikit-learn", "scipy", "numpy", "anthropic", "pytest", "dbt-databricks"):
        assert heavy not in pins, heavy
    for needed in ("fastapi", "starlette", "uvicorn", "duckdb"):
        assert needed in pins, needed


def test_A13_every_package_the_public_app_loads_is_pinned(tmp_path):
    # Imports the public app in a fresh process, from a folder that is not the repo, and maps every module it
    # loads to the package that ships it. Each such package must be in requirements.txt.
    script = (
        "import sys, importlib.metadata as md\n"
        f"sys.path.insert(0, {str(REPO / 'src')!r})\n"
        "before = set(sys.modules)\n"
        "import voc.public\n"
        "mods = {m.split('.')[0] for m in set(sys.modules) - before}\n"
        "dist = md.packages_distributions()\n"
        "print('\\n'.join(sorted({d.lower() for m in mods for d in dist.get(m, [])})))\n")
    import os
    import subprocess

    env = {**os.environ, "WEBSITE_HOSTNAME": HOST}
    result = subprocess.run([sys.executable, "-c", script], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    loaded = {name.replace("_", "-") for name in result.stdout.split()}
    pinned = {name.replace("_", "-") for name in _pins()}
    assert loaded and loaded <= pinned, loaded - pinned


def test_A13_an_empty_host_name_is_refused(monkeypatch):
    monkeypatch.setenv("WEBSITE_HOSTNAME", "")
    sys.modules.pop("voc.public", None)
    try:
        with pytest.raises(RuntimeError, match="WEBSITE_HOSTNAME"):
            importlib.import_module("voc.public")
    finally:
        sys.modules.pop("voc.public", None)


def test_A13_the_public_app_finds_the_results_whatever_folder_it_starts_in(monkeypatch, tmp_path):
    monkeypatch.setenv("WEBSITE_HOSTNAME", HOST)
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("voc.public", None)
    try:
        public = importlib.import_module("voc.public")
        versions = _client(public.app).get("/api/versions").json()
        assert versions and versions[0]["Prompt"] == "v1"
    finally:
        sys.modules.pop("voc.public", None)


def test_A13_the_complaint_view_says_whether_a_review_can_be_saved(root):
    from voc.api import create_app

    public = _client(_public(root)).get("/api/review/v1/complaint/SYN-3").json()
    local = _client(create_app(root), "127.0.0.1").get("/api/review/v1/complaint/SYN-3").json()
    assert public["can_review"] is False and local["can_review"] is True


def test_A13_the_page_says_where_reviews_are_made_on_the_public_copy():
    script = (REPO / "src" / "voc" / "web" / "app.js").read_text(encoding="utf-8")
    assert "Reviews are made on the analyst's own machine" in script and "can_review" in script


def test_A13_the_deploy_guide_names_no_local_folder_and_uploads_no_lock_file():
    guide = (REPO / "docs" / "DEPLOY.md").read_text(encoding="utf-8")
    assert not re.search(r"[A-Za-z]:\\Users\\", guide)
    archive = next(line for line in guide.splitlines() if line.startswith("git archive"))
    assert ":!uv.lock" in archive and ":!pyproject.toml" in archive
