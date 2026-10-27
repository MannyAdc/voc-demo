"""B7: tests cannot reach the network, and never see a real API key.

Every target here is reserved and can never reach a real server, so even a
failing run of these tests stays offline: 192.0.2.1 is a documentation address
(RFC 5737) and the .invalid name never resolves (RFC 2606).
"""
import os
import socket
import urllib.request

import pytest

from conftest import scrub_environment

OUTSIDE = ("192.0.2.1", 443)


def test_B7_a_socket_cannot_connect_outside():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(RuntimeError, match="network access is blocked"):
            s.connect(OUTSIDE)
    finally:
        s.close()


def test_B7_create_connection_is_blocked():
    with pytest.raises(RuntimeError, match="network access is blocked"):
        socket.create_connection(OUTSIDE, timeout=1)


def test_B7_name_lookup_is_blocked():
    with pytest.raises(RuntimeError, match="network access is blocked"):
        socket.getaddrinfo("blocked.invalid", 443)


def test_B7_a_web_request_is_blocked():
    with pytest.raises(RuntimeError, match="network access is blocked"):
        urllib.request.urlopen("http://192.0.2.1/", timeout=1)


def test_B7_loopback_still_works_so_local_test_servers_can_run():
    a, b = socket.socketpair()
    try:
        a.sendall(b"ok")
        assert b.recv(2) == b"ok"
    finally:
        a.close()
        b.close()


def test_B7_the_api_key_is_removed_from_the_test_environment():
    fake_key = "sk-" + "ant-" + "x" * 20  # built at run time, never one string
    cleaned = scrub_environment({"ANTHROPIC_API_KEY": fake_key, "PATH": "kept"})
    assert cleaned == {"PATH": "kept"}


def test_B7_tests_run_without_an_api_key():
    assert "ANTHROPIC_API_KEY" not in os.environ
