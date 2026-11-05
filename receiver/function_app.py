"""Spec 004, J9: the receiver's two functions, an HTTP function that takes the calls and a queue function that does
the work. The HTTP functions are open at the HTTP level, with no function key in the URL: their own HTTP Basic
sign-in and signature checks are the access control (J16, owner decision of 5 November). The logic is in
`receiver_core`, the links to the services in `receiver_adapters`.
"""
import json
import logging
import os
import time

import azure.functions as func

from receiver_adapters import DatabricksClient, GitHubClient, StorageQueue, TableStore
from receiver_core import Settings, handle_http, handle_queue

QUEUE = "june-events"
KEPT_DAYS = 30

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


def _settings():
    return Settings(basic_user=os.environ["VOC_BASIC_USER"], basic_password=os.environ["VOC_BASIC_PASSWORD"],
                    hmac_secret=os.environ["VOC_HMAC_SECRET"].encode("utf-8"),
                    job_a_job_id=int(os.environ["VOC_JOB_A_JOB_ID"]))


def _log(event, **fields):
    logging.info(json.dumps({"event": event, **fields}, sort_keys=True))


def _http(route, req):
    reply = handle_http(route, dict(req.headers), req.get_body(), _settings(), TableStore.from_env(),
                        StorageQueue.from_env(QUEUE), int(time.time()), _log)
    return func.HttpResponse(status_code=reply.status)


@app.route(route="databricks", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def databricks(req: func.HttpRequest) -> func.HttpResponse:
    return _http("databricks", req)


@app.route(route="result", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def result(req: func.HttpRequest) -> func.HttpResponse:
    return _http("result", req)


@app.queue_trigger(arg_name="msg", queue_name=QUEUE, connection="VOC_STORAGE")
def work(msg: func.QueueMessage) -> None:
    store = TableStore.from_env()
    store.purge_older_than_days(KEPT_DAYS)
    handle_queue(json.loads(msg.get_body().decode("utf-8")), _settings(), DatabricksClient.from_env(),
                 GitHubClient.from_env(), store, _log)
