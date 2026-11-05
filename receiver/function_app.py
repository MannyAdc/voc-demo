"""Spec 004, J9: the receiver's two functions, an HTTP function that takes the calls and a queue function that does
the work. The HTTP functions are open at the HTTP level, with no function key in the URL: their own HTTP Basic
sign-in and signature checks are the access control (J16, owner decision of 5 November). The logic is in
`receiver_core`, the links to the services in `receiver_adapters`.

The settings and the service clients are made once per instance, on first use. A client makes no call until the
logic uses it, so a refused request costs no token or storage call (review of #91).
"""
import functools
import json
import logging
import os
import time

import azure.functions as func

from receiver_adapters import DatabricksClient, GitHubClient, StorageQueue, TableStore
from receiver_core import handle_http, handle_queue, load_settings, purge_safely

QUEUE = "june-events"
KEPT_DAYS = 30

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


@functools.cache
def _settings():
    return load_settings(os.environ)  # refuses an empty or unresolved Key Vault secret


@functools.cache
def _store():
    return TableStore.from_env()


@functools.cache
def _queue():
    return StorageQueue.from_env(QUEUE)


def _log(event, **fields):
    logging.info(json.dumps({"event": event, **fields}, sort_keys=True))


def _http(route, req):
    reply = handle_http(route, dict(req.headers), req.get_body(), _settings(), _store(), _queue(), int(time.time()),
                        _log)
    return func.HttpResponse(status_code=reply.status)


@app.route(route="databricks", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def databricks(req: func.HttpRequest) -> func.HttpResponse:
    return _http("databricks", req)


@app.route(route="result", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def result(req: func.HttpRequest) -> func.HttpResponse:
    return _http("result", req)


@app.queue_trigger(arg_name="msg", queue_name=QUEUE, connection="VOC_STORAGE")
def work(msg: func.QueueMessage) -> None:
    purge_safely(_store(), KEPT_DAYS, _log)
    handle_queue(json.loads(msg.get_body().decode("utf-8")), _settings(), DatabricksClient.from_env(),
                 GitHubClient.from_env(), _store(), _log)
