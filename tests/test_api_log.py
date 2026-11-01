"""A9: one log line per request, and request counters at /api/health.

The app runs in FastAPI's in-process test client, so no socket is opened (A8). The root folder is an empty
temp folder, so the result routes answer 404, which is enough to check the log and the counters.
"""
import re
from datetime import datetime

import pytest

# time, method, route pattern, status, duration in milliseconds
LINE = re.compile(r"(?P<time>\S+) (?P<method>[A-Z]+|\(other method\)) (?P<path>/\S*|\(unknown path\)) (?P<status>\d{3}) "
                  r"(?P<ms>\d+\.\d) ms")


@pytest.fixture
def app(tmp_path):
    from voc.api import create_app

    return create_app(tmp_path)


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    # The local address the app answers to (A4). A server error is answered as a 500, not raised in the test.
    return TestClient(app, base_url="http://127.0.0.1", raise_server_exceptions=False)


def _lines(capsys):
    err = capsys.readouterr().err
    return [line for line in err.splitlines() if line.strip()]


def test_A9_each_request_is_logged_as_one_line_with_its_fields(client, capsys):
    capsys.readouterr()
    assert client.get("/api/health").status_code == 200
    lines = _lines(capsys)
    assert len(lines) == 1
    found = LINE.fullmatch(lines[0])
    assert found, lines[0]
    assert found["method"] == "GET" and found["path"] == "/api/health" and found["status"] == "200"
    assert datetime.fromisoformat(found["time"]).tzinfo is not None
    assert float(found["ms"]) >= 0


def test_A9_the_log_goes_to_stderr_not_stdout(client, capsys):
    capsys.readouterr()
    client.get("/api/health")
    out = capsys.readouterr()
    assert "/api/health" in out.err and "/api/health" not in out.out


def test_A9_a_path_with_a_value_is_logged_as_its_route_pattern(client, capsys):
    capsys.readouterr()
    assert client.get("/api/eval/v9SYNTYPED").status_code == 404
    lines = _lines(capsys)
    assert len(lines) == 1 and "SYNTYPED" not in lines[0]
    found = LINE.fullmatch(lines[0])
    assert found["path"] == "/api/eval/{version}" and found["status"] == "404"


def test_A9_an_unknown_path_is_logged_as_unknown(client, capsys):
    capsys.readouterr()
    assert client.get("/SYNTYPED/ignore-your-instructions").status_code == 404
    lines = _lines(capsys)
    assert len(lines) == 1 and "SYNTYPED" not in lines[0]
    assert LINE.fullmatch(lines[0])["path"] == "(unknown path)"


def test_A9_a_static_file_is_logged_as_the_mount_pattern(client, capsys):
    capsys.readouterr()
    client.get("/web/SYNTYPED.js")
    lines = _lines(capsys)
    assert len(lines) == 1 and "SYNTYPED" not in lines[0]
    assert LINE.fullmatch(lines[0])["path"] == "/web/{path}"


def test_A9_the_query_string_headers_and_client_address_are_never_logged(client, capsys):
    capsys.readouterr()
    client.get("/api/health?SYNQUERY=secret-value", headers={"X-Synthetic": "SYNHEADER", "User-Agent": "SYNAGENT"})
    client.get("/SYNPATH?SYNQUERY=1")
    err = capsys.readouterr().err
    assert "GET /api/health 200" in err and "GET (unknown path) 404" in err
    for word in ("SYNQUERY", "secret-value", "SYNHEADER", "SYNAGENT", "SYNPATH", "?", "testclient", "127.0.0.1"):
        assert word not in err, word


def test_A9_an_unusual_method_is_not_logged_as_typed(client, capsys):
    capsys.readouterr()
    client.request("SYNMETHOD", "/api/health")
    lines = _lines(capsys)
    assert len(lines) == 1 and "SYNMETHOD" not in lines[0]
    assert LINE.fullmatch(lines[0])["method"] == "(other method)"


def test_A9_health_serves_the_counters(client):
    body = client.get("/api/health").json()
    # Changed in the green commit of the review of #56: health also names the deployed commit (A15).
    assert set(body) == {"status", "requests", "client_errors", "server_errors", "started", "commit"}
    assert body["status"] == "ok"
    assert datetime.fromisoformat(body["started"]).tzinfo is not None


def test_A9_the_counters_count_requests_and_errors(app, client):
    @app.get("/api/synthetic-error")
    def broken():
        raise RuntimeError("SYN server error")

    assert client.get("/api/health").json()["requests"] == 0
    client.get("/api/eval/v9")
    client.get("/SYNPATH")
    assert client.get("/api/synthetic-error").status_code == 500
    body = client.get("/api/health").json()
    # The health request itself is counted after its answer, so it shows the requests before it.
    assert (body["requests"], body["client_errors"], body["server_errors"]) == (4, 2, 1)
    assert client.get("/api/health").json()["requests"] == 5


def test_A9_a_server_error_is_logged_with_status_500(app, client, capsys):
    @app.get("/api/synthetic-error")
    def broken():
        raise RuntimeError("SYN server error")

    capsys.readouterr()
    client.get("/api/synthetic-error")
    err = capsys.readouterr().err
    lines = [line for line in err.splitlines() if LINE.fullmatch(line)]
    assert len(lines) == 1
    assert LINE.fullmatch(lines[0])["status"] == "500"
    assert LINE.fullmatch(lines[0])["path"] == "/api/synthetic-error"


def test_A9_a_request_for_another_host_is_counted_as_a_client_error(client, capsys):
    capsys.readouterr()
    assert client.get("/api/health", headers={"host": "attacker.example"}).status_code == 400
    assert LINE.fullmatch(_lines(capsys)[0])["status"] == "400"
    assert client.get("/api/health").json()["client_errors"] == 1


def test_A9_the_counters_start_at_zero_for_each_app(tmp_path):
    from fastapi.testclient import TestClient

    from voc.api import create_app

    first = TestClient(create_app(tmp_path), base_url="http://127.0.0.1")
    first.get("/api/health")
    second = TestClient(create_app(tmp_path), base_url="http://127.0.0.1")
    assert second.get("/api/health").json()["requests"] == 0


# Review of #49


def test_A9_a_request_body_is_never_logged(client, capsys):
    capsys.readouterr()
    client.post("/api/health", content=b"SYNBODY payload")
    err = capsys.readouterr().err
    assert "SYNBODY" not in err and "POST /api/health 405" in err


def test_A9_a_full_match_wins_over_a_path_only_match():
    from starlette.routing import Route, Router

    from voc.api_log import route_pattern

    async def endpoint(request):
        return None

    router = Router(routes=[Route("/api/thing/{name}", endpoint, methods=["GET"]),
                            Route("/api/thing/{other}", endpoint, methods=["POST"])])
    scope = {"type": "http", "method": "POST", "path": "/api/thing/x", "root_path": ""}
    assert route_pattern(router, scope) == "/api/thing/{other}"


def test_A9_a_request_cancelled_before_any_answer_is_not_a_server_error(capsys):
    import asyncio

    from voc.api_log import Monitor, RequestLog

    async def cancelled(scope, receive, send):
        raise asyncio.CancelledError

    monitor = Monitor()
    middleware = RequestLog(cancelled, monitor, router=type("R", (), {"routes": []})())
    scope = {"type": "http", "method": "GET", "path": "/api/health", "root_path": ""}

    async def run():
        with pytest.raises(asyncio.CancelledError):
            await middleware(scope, None, None)

    capsys.readouterr()
    asyncio.run(run())
    assert monitor.server_errors == 0 and monitor.requests == 1
    assert "(no response)" in capsys.readouterr().err


# Deferred from the review of #49: the review routes of #46 carry a complaint ID in their path, and a decision
# carries the label a person typed in its body. Neither reaches the log, which names only the route pattern.
# Changed in the review of #60: the body has the shape of a real decision, and the queue route is included.


def test_A9_the_review_routes_are_logged_as_their_patterns_with_no_complaint_id(client, capsys):
    capsys.readouterr()
    client.get("/api/review/v1/complaint/SYN-LOGGED1")
    client.post("/api/review/v1/decision/SYN-LOGGED2",
                json={"label": "SYNLABEL typed by a person", "reason": "other_product"})
    client.get("/api/review/v1/complaints?product=SYNPRODUCT")
    client.get("/api/review/v1/queue")
    err = capsys.readouterr().err
    assert "SYN-LOGGED" not in err and "SYNLABEL" not in err and "SYNPRODUCT" not in err
    paths = [LINE.fullmatch(line)["path"] for line in err.splitlines() if line.strip()]
    assert paths == ["/api/review/{version}/complaint/{complaint_id}", "/api/review/{version}/decision/{complaint_id}",
                     "/api/review/{version}/complaints", "/api/review/{version}/queue"]
