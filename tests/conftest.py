"""Shared test setup (B7): block the network and remove real keys.

Loopback stays open, because local test servers and Windows socket pairs
need it. Anything else raises before a packet can leave the machine.
"""
import ipaddress
import socket

import pytest

SECRET_VARS = ("ANTHROPIC_API_KEY",)


def scrub_environment(env):
    """Return a copy of env without secret variables. Also used for subprocesses."""
    return {name: value for name, value in env.items() if name not in SECRET_VARS}


def _is_loopback(host):
    if host is None or host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _refuse(target):
    raise RuntimeError(f"network access is blocked in tests: {target!r}")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo
    real_create_connection = socket.create_connection

    def connect(self, address):
        if isinstance(address, tuple) and not _is_loopback(address[0]):
            _refuse(address)
        return real_connect(self, address)

    def connect_ex(self, address):
        if isinstance(address, tuple) and not _is_loopback(address[0]):
            _refuse(address)
        return real_connect_ex(self, address)

    def getaddrinfo(host, *args, **kwargs):
        if not _is_loopback(host):
            _refuse(host)
        return real_getaddrinfo(host, *args, **kwargs)

    def create_connection(address, *args, **kwargs):
        if not _is_loopback(address[0]):
            _refuse(address)
        return real_create_connection(address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(socket, "create_connection", create_connection)


@pytest.fixture(autouse=True)
def no_secrets(monkeypatch):
    for name in SECRET_VARS:
        monkeypatch.delenv(name, raising=False)
