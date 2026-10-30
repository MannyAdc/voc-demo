"""The analyst screens (docs/USER.md tasks 2 and 3, specs/002-results-api-dashboard A10 to A12).

Changed on 30 October (owner decision A): the screens use the development set, never the test set (B17, B20),
and the complaint text needs `voc serve --with-text`.

Every test builds a temp project from the committed synthetic fixture (SYN- IDs): a staged table loaded with
the same load code as `voc load`, and synthetic development results that point into it. The app runs in FastAPI's
in-process test client, so no socket is opened (A8).
"""
import csv
import io
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from voc.labels import load_labels
from voc.load import DB_PATH, load_month

REPO = Path(__file__).resolve().parents[1]
WEB = REPO / "src" / "voc" / "web"
FIXTURE = REPO / "tests" / "fixtures" / "dbt" / "complaints.csv"
HEADER = {"X-Requested-With": "voc"}
COLUMNS = ("complaint_id", "split", "prompt_version", "proposed_label", "quote_start", "quote_end", "decision",
           "reason", "accepted_label", "tfidf_label", "tfidf_confidence", "recording_key")


def _fixture_rows():
    with open(FIXTURE, encoding="utf-8", newline="") as f:
        return [row for row in csv.DictReader(f) if row["Consumer complaint narrative"].strip()]


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _results(rows):
    """Synthetic development results: the first row accepted with a real quote, the rest quarantined."""
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    for i, row in enumerate(rows):
        text, product, cid = row["Consumer complaint narrative"], row["Product"], row["Complaint ID"]
        base = {"complaint_id": cid, "split": "dev", "prompt_version": "v1", "tfidf_label": product,
                "tfidf_confidence": "0.9", "recording_key": "0" * 64}
        if i == 0:
            word = re.search(r"[A-Za-z]{4,}(?: [A-Za-z]+){2}", text)
            writer.writerow({**base, "proposed_label": product, "quote_start": word.start(), "quote_end": word.end(),
                             "decision": "accepted", "reason": "", "accepted_label": product})
        elif i == 1:
            writer.writerow({**base, "proposed_label": "Mortgage", "quote_start": "", "quote_end": "",
                             "decision": "quarantined", "reason": "quote_not_in_text", "accepted_label": ""})
        else:
            writer.writerow({**base, "proposed_label": "", "quote_start": "", "quote_end": "",
                             "decision": "quarantined", "reason": "unparseable", "accepted_label": ""})
    return out.getvalue()


@pytest.fixture
def rows():
    return _fixture_rows()[:4]


@pytest.fixture
def root(tmp_path, rows):
    root = tmp_path / "repo"
    labels = (REPO / "config" / "labels.toml").read_text(encoding="utf-8")
    _write(root / "config" / "labels.toml", labels)
    _write(root / "results" / "eval" / "v1_dev.csv", _results(rows))
    names = [label.name for label in load_labels(root / "config" / "labels.toml")]
    load_month(root / DB_PATH, FIXTURE, "july_2026", names)
    return root


def _client(root, with_text=True):
    from fastapi.testclient import TestClient

    from voc.api import create_app

    return TestClient(create_app(root, with_text=with_text), base_url="http://127.0.0.1")


@pytest.fixture
def client(root):
    # The owner's own run, `voc serve --with-text`. The tests without the flag build their own client.
    return _client(root)


# A10: the complaint's text, on the analyst's own machine only


def test_A10_one_complaint_serves_its_text_and_quote_positions_on_the_local_machine(client, rows):
    first = rows[0]
    got = client.get(f"/api/review/v1/complaint/{first['Complaint ID']}").json()
    assert got["local"] is True
    assert got["text"] == first["Consumer complaint narrative"][:4000]
    start, end = got["quote"]["start"], got["quote"]["end"]
    assert 0 <= start < end <= len(got["text"]) and got["ai_label"] == first["Product"]


def test_A10_without_the_local_data_no_text_and_no_consumer_choice_is_served(root, rows):
    (root / DB_PATH).unlink()
    got = _client(root).get(f"/api/review/v1/complaint/{rows[0]['Complaint ID']}").json()
    assert got["local"] is False and got["text"] is None and got["consumer_choice"] is None
    assert got["ai_label"] == rows[0]["Product"]


def test_A10_a_complaint_outside_the_development_results_is_a_404_even_if_it_is_staged(client):
    staged_only = [r for r in csv.DictReader(open(FIXTURE, encoding="utf-8"))][-1]["Complaint ID"]
    assert client.get(f"/api/review/v1/complaint/{staged_only}").status_code == 404
    assert client.get("/api/review/v1/complaint/not-an-id").status_code == 404


def test_A2_the_lists_never_serve_complaint_text(client, rows):
    for path in ("/api/review/v1/complaints", "/api/review/v1/queue"):
        text = client.get(path).text
        for row in rows:
            assert row["Consumer complaint narrative"] not in text


# A11: the product list, and the consumer's choice hidden while a person decides


def test_A11_the_list_holds_labels_and_the_consumer_choice_but_hides_it_on_unreviewed_quarantine(client, rows):
    got = client.get("/api/review/v1/complaints").json()
    assert got["local"] is True and got["total"] == len(rows)
    by_id = {r["complaint_id"]: r for r in got["rows"]}
    first, second = by_id[rows[0]["Complaint ID"]], by_id[rows[1]["Complaint ID"]]
    assert first["consumer_choice"] == rows[0]["Product"] and first["ai_label"] == rows[0]["Product"]
    assert second["decision"] == "quarantined" and second["consumer_choice"] is None and second["hidden"] is True


def test_A11_the_list_filters_by_product_and_by_right_or_wrong(client, rows):
    product = rows[0]["Product"]
    got = client.get("/api/review/v1/complaints", params={"product": product}).json()
    assert {r["complaint_id"] for r in got["rows"]} == {r["Complaint ID"] for r in rows if r["Product"] == product}
    right = client.get("/api/review/v1/complaints", params={"show": "right"}).json()
    assert [r["complaint_id"] for r in right["rows"]] == [rows[0]["Complaint ID"]]
    quarantined = client.get("/api/review/v1/complaints", params={"show": "quarantined"}).json()
    assert len(quarantined["rows"]) == len(rows) - 1


def test_A11_the_list_pages_by_25_and_refuses_a_bad_filter(client):
    got = client.get("/api/review/v1/complaints", params={"page": 1}).json()
    assert got["page"] == 1 and got["per_page"] == 25 and got["pages"] == 1
    assert client.get("/api/review/v1/complaints", params={"show": "everything"}).status_code == 422
    assert client.get("/api/review/v1/complaints", params={"product": "SYN not a product"}).status_code == 404
    assert client.get("/api/review/v1/complaints", params={"page": 0}).status_code == 422


def test_A11_a_quarantined_complaint_hides_the_consumer_choice_until_it_is_reviewed(client, rows):
    cid = rows[1]["Complaint ID"]
    before = client.get(f"/api/review/v1/complaint/{cid}").json()
    assert before["consumer_choice"] is None and before["hidden"] is True and before["text"]
    assert client.post(f"/api/review/v1/decision/{cid}", headers=HEADER,
                       json={"label": rows[1]["Product"], "reason": "word_model_right"}).status_code == 200
    after = client.get(f"/api/review/v1/complaint/{cid}").json()
    assert after["consumer_choice"] == rows[1]["Product"] and after["hidden"] is False


# A12: a review decision is stored and served


def test_A12_a_review_is_stored_in_the_results_folder_and_served(root, client, rows):
    cid = rows[2]["Complaint ID"]
    response = client.post(f"/api/review/v1/decision/{cid}", headers=HEADER,
                           json={"label": "Credit card", "reason": "other_product"})
    assert response.status_code == 200
    with open(root / "results" / "reviews" / "v1_dev.csv", encoding="utf-8", newline="") as f:
        stored = list(csv.DictReader(f))
    assert [(r["complaint_id"], r["label"], r["reason"]) for r in stored] == [(cid, "Credit card", "other_product")]
    assert set(stored[0]) == {"complaint_id", "label", "reason", "decided_at"}
    queue = client.get("/api/review/v1/queue").json()
    assert queue["reviewed"] == 1 and queue["total"] == len(rows) - 1
    assert client.get(f"/api/review/v1/complaint/{cid}").json()["review"]["label"] == "Credit card"


def test_A12_a_second_decision_replaces_the_first(root, client, rows):
    cid = rows[2]["Complaint ID"]
    for label, reason in (("Credit card", "other_product"), (None, "no_product")):
        assert client.post(f"/api/review/v1/decision/{cid}", headers=HEADER,
                           json={"label": label, "reason": reason}).status_code == 200
    text = (root / "results" / "reviews" / "v1_dev.csv").read_text(encoding="utf-8")
    assert text.count(cid) == 1 and ",no_product," in text


@pytest.mark.parametrize("body", [
    {"label": "Credit card", "reason": "SYN free text"},
    {"label": "SYN not a product", "reason": "other_product"},
    {"label": None, "reason": "other_product"},
    {"label": "Credit card", "reason": "no_product"},
    {"label": "Mortgage", "reason": "word_model_right"},
    {"label": "Credit card", "reason": "ai_right"},
])
def test_A12_a_review_that_does_not_fit_its_reason_is_refused(root, client, rows, body):
    cid = rows[1]["Complaint ID"]  # SYN-3: the AI proposed Mortgage, the word-based model says Credit card
    response = client.post(f"/api/review/v1/decision/{cid}", headers=HEADER, json=body)
    assert response.status_code in (400, 422)
    assert not (root / "results" / "reviews" / "v1_dev.csv").exists()


def test_A12_only_a_quarantined_development_complaint_can_be_reviewed(client, rows):
    body = {"label": rows[0]["Product"], "reason": "other_product"}
    assert client.post(f"/api/review/v1/decision/{rows[0]['Complaint ID']}", headers=HEADER, json=body).status_code == 409
    assert client.post("/api/review/v1/decision/SYN-999999", headers=HEADER, json=body).status_code == 404


def test_A12_a_review_needs_the_page_header_so_another_site_cannot_send_one(root, client, rows):
    cid = rows[2]["Complaint ID"]
    body = {"label": "Credit card", "reason": "other_product"}
    assert client.post(f"/api/review/v1/decision/{cid}", json=body).status_code == 403
    assert client.post(f"/api/review/v1/decision/{cid}", headers=HEADER,
                       content="label=Credit+card&reason=other_product",
                       ).status_code in (403, 415, 422)
    assert not (root / "results" / "reviews" / "v1_dev.csv").exists()


def test_A12_the_reviews_file_can_be_committed(tmp_path):
    # The reviews file holds IDs, labels and fixed reasons only, so it is a results file that git keeps.
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    shutil.copy(REPO / ".gitignore", tmp_path / ".gitignore")
    result = subprocess.run(["git", "check-ignore", "-q", "results/reviews/v1_dev.csv"], cwd=tmp_path)
    assert result.returncode == 1


def test_A12_no_other_route_accepts_a_write(client):
    for path in ("/api/review/v1/complaints", "/api/review/v1/queue", "/api/review/v1/complaint/SYN-1"):
        assert client.post(path, headers=HEADER).status_code == 405


# A7: the page explains what is labelled, and why the consumer's choice is hidden


def test_A7_the_page_explains_what_is_labelled_with_the_three_names():
    page = (WEB / "index.html").read_text(encoding="utf-8")
    assert "What is being labelled" in page
    for name in ("The AI's label", "word-based model", "consumer's own choice"):
        assert name in page, name


def test_A7_the_review_screen_says_why_the_consumer_choice_is_hidden():
    text = (WEB / "index.html").read_text(encoding="utf-8") + (WEB / "app.js").read_text(encoding="utf-8")
    assert "hidden while you decide" in text


def test_A7_every_review_control_has_a_label():
    page = (WEB / "index.html").read_text(encoding="utf-8")
    for control in re.findall(r"<(?:select|input)[^>]*>", page):
        ident = re.search(r'id="([^"]+)"', control)
        assert ident and (f'for="{ident.group(1)}"' in page or "aria-label" in control), control


# Added on 30 October (owner decision A): the development set only, and the text only with --with-text


def test_A10_without_the_flag_no_text_is_served_but_the_labels_are(root, rows):
    got = _client(root, with_text=False).get(f"/api/review/v1/complaint/{rows[0]['Complaint ID']}").json()
    assert got["text"] is None and got["with_text"] is False
    assert got["local"] is True and got["consumer_choice"] == rows[0]["Product"]


def test_A10_voc_serve_passes_the_text_flag_only_when_asked(root, monkeypatch):
    import uvicorn

    from voc import api, cli

    seen = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: None)
    real = api.create_app
    monkeypatch.setattr(api, "create_app", lambda r, with_text=False: seen.append(with_text) or real(r, with_text))
    assert cli.main(["serve"], env={}, root=root) == 0
    assert cli.main(["serve", "--with-text"], env={}, root=root) == 0
    assert seen == [False, True]


def test_A10_the_test_set_is_never_served_by_the_review_routes(root, rows):
    # B17: the review routes read the development results only, so a test results file is never looked at.
    dev = root / "results" / "eval" / "v1_dev.csv"
    dev.rename(root / "results" / "eval" / "v1_test.csv")
    client = _client(root)
    assert client.get("/api/review/v1/complaints").status_code == 404
    assert client.get(f"/api/review/v1/complaint/{rows[0]['Complaint ID']}").status_code == 404


def test_A10_claude_md_says_claude_never_passes_the_text_flag():
    text = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
    assert "--with-text" in text
