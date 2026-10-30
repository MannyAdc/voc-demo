"""A9: one log line per request on stderr, and request counters for `/api/health`.

A line holds the time, the method, the route pattern, the status code and the duration in milliseconds.
It never holds the query string, a header, the body or the client address. The path is logged as the
pattern of the route it matched, such as `/api/eval/{version}`, or as `(unknown path)`, so nothing a
caller typed reaches the log. The counters live in memory and start again at zero with each app.
"""
import asyncio
import sys
import time
from datetime import datetime, timezone

from starlette.routing import Match, Mount

UNKNOWN_PATH = "(unknown path)"
OTHER_METHOD = "(other method)"
NO_RESPONSE = "(no response)"
METHODS = {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Monitor:
    """Counts the requests answered since the app started."""

    def __init__(self):
        self.started = _now()
        self.requests = self.client_errors = self.server_errors = 0

    def count_no_response(self):
        """A request cancelled before any answer: counted, but not as an error."""
        self.requests += 1

    def count(self, status):
        self.requests += 1
        if 400 <= status < 500:
            self.client_errors += 1
        elif status >= 500:
            self.server_errors += 1

    def health(self):
        """The body of `/api/health`. A request is counted after its answer, so this one is not in it yet."""
        return {"status": "ok", "requests": self.requests, "client_errors": self.client_errors,
                "server_errors": self.server_errors, "started": self.started}


def route_pattern(router, scope):
    """The pattern of the route that matches this path and method, or else of the first route that matches the
    path only, or `(unknown path)`. Review of #49: a full match wins, as in the router itself."""
    partial = None
    for route in router.routes:
        match, _ = route.matches(dict(scope))
        if match == Match.NONE:
            continue
        pattern = f"{route.path}/{{path}}" if isinstance(route, Mount) else route.path
        if match == Match.FULL:
            return pattern
        partial = partial or pattern
    return partial or UNKNOWN_PATH


class RequestLog:
    """ASGI middleware: logs one line per HTTP request to stderr and counts it in the monitor."""

    def __init__(self, app, monitor, router):
        self.app, self.monitor, self.router = app, monitor, router

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = time.perf_counter()
        # Read before the app runs, because the router changes the scope as it matches.
        path = route_pattern(self.router, scope)
        method = scope["method"] if scope["method"] in METHODS else OTHER_METHOD
        status = 500  # an error before the answer starts is answered as a 500 by the server error handler

        async def send_and_note(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        answered = False

        async def send_and_mark(message):
            nonlocal answered
            if message["type"] == "http.response.start":
                answered = True
            await send_and_note(message)

        try:
            await self.app(scope, receive, send_and_mark)
        except asyncio.CancelledError:
            # Review of #49: a request cancelled before any answer (for example at shutdown) is no server error.
            if not answered:
                status = None
            raise
        finally:
            ms = (time.perf_counter() - start) * 1000
            if status is None:
                self.monitor.count_no_response()
                print(f"{_now()} {method} {path} {NO_RESPONSE} {ms:.1f} ms", file=sys.stderr, flush=True)
            else:
                self.monitor.count(status)
                print(f"{_now()} {method} {path} {status} {ms:.1f} ms",
                      file=sys.stderr, flush=True)


def install(app):
    """Add the request log to a FastAPI app. Returns its monitor, for `/api/health`."""
    monitor = Monitor()
    app.add_middleware(RequestLog, monitor=monitor, router=app.router)
    return monitor
