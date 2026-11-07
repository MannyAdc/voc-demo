"""Spec 004, J9: the owner's live check of the deployed receiver (owner decisions, 6 and 7 November).

Usage, in the owner's own PowerShell, from the repo's folder:

    uv run --locked --native-tls python scripts/receiver_live_check.py https://<the receiver's address>

It asks for the HMAC secret with a hidden prompt. The secret is never an argument, since PowerShell keeps command
lines in its history file on disk. It sends two synthetic result messages to the receiver's result route:
- one signed with a wrong key, which the receiver must refuse with 401, since it checks the signature first
- one signed with the secret, which the receiver must queue (202)

The message names no real run: GitHub run 1, Job A run 1, Job B never started, and as its attempt the Unix time of
this check, so each run has a fresh key and is never taken as a duplicate. A 202 means the message was queued. The
proof that it was stored is the `result` row in the receiver's table, with the key it prints, which the owner
checks and then deletes, with its `event` row (docs/RECEIVER_STEPS.md). It prints the two status codes, a verdict
and the key only, never the secret. A Python string cannot be wiped from memory, so the script drops the secret
straight after signing and exits, which frees it. It uses Python's standard library only.
"""
import getpass
import hashlib
import hmac
import http.client
import json
import re
import sys
import time
import urllib.error
import urllib.request

CONTRACT = "voc-june-1"
ADDRESS = re.compile(r"https://[a-z0-9.-]+")


def message_bytes(now):
    """A synthetic result message for this check, as the contract's exact bytes (J16 item 9)."""
    body = {"contract": CONTRACT, "github_run_id": 1, "github_run_attempt": int(now), "job_a_run_id": 1,
            "job_b_run_id": None, "result_state": "NOT_STARTED", "job_b_exit": None}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def signed_headers(key, timestamp, raw):
    stamp = str(int(timestamp))
    signature = hmac.new(key.encode("utf-8"), stamp.encode("ascii") + b"." + raw, hashlib.sha256).hexdigest()
    return {"X-Voc-Timestamp": stamp, "X-Voc-Signature": f"sha256={signature}", "Content-Type": "application/json"}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is refused, so the signed message never goes to another host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _post(url, raw, headers):
    request = urllib.request.Request(url, data=raw, headers=headers, method="POST")
    try:
        with _OPENER.open(request, timeout=30) as reply:
            return reply.status
    except urllib.error.HTTPError as err:
        return err.code
    except (OSError, http.client.HTTPException):
        return 0


def main(argv):
    if len(argv) != 1 or not ADDRESS.fullmatch(argv[0]):
        print("usage: receiver_live_check.py https://<the receiver's address>, with no path and no other argument")
        return 2
    url = argv[0] + "/api/result"
    secret = getpass.getpass("The receiver's HMAC secret (hidden): ")
    now = int(time.time())
    raw = message_bytes(now)
    good = signed_headers(secret, now, raw)
    del secret
    bad = signed_headers("not the secret", now, raw)
    refused = _post(url, raw, bad)
    taken = _post(url, raw, good)
    print(f"badly signed: HTTP {refused} (must be 401)")
    print(f"signed: HTTP {taken} (must be 202: queued)")
    passed = refused == 401 and taken == 202
    key = f"1:{now}"
    if passed:
        print(f"verdict: PASS, queued under the key {key}")
        print(f"Now check the receiver's table for the result row {key}, then delete it and the event row {key}.")
    else:
        print("verdict: FAIL")
        if taken == 401:
            print("A 401 for the signed message means a wrong secret, or this laptop's clock more than 5 minutes behind "
                  "or 1 minute ahead.")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
