"""Shared test setup (B7): block the network and remove real credentials.

Everything is switched on in pytest_configure, before any test file is
imported, and switched off again in pytest_unconfigure. Loopback stays open,
because local test servers and Windows socket pairs need it.

Not covered here: DuckDB and dbt make their own network calls outside
Python sockets. DuckDB extension auto-install is turned off where the
connection is made (task T010). dbt usage stats are turned off below.
"""
import asyncio
import ipaddress
import os
import socket
import sys

import pytest

CREDENTIAL_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN")
QUIET_TOOL_VARS = {"DBT_SEND_ANONYMOUS_USAGE_STATS": "False", "DO_NOT_TRACK": "1"}

_saved_attrs = []
_saved_env = {}


def _is_loopback(host):
    if host is None or host == "localhost":
        return True
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _check(address):
    if isinstance(address, tuple) and not _is_loopback(address[0]):
        raise RuntimeError(f"network access is blocked in tests: {address!r}")


def _guard_address(real):
    def guarded(self, address):
        _check(address)
        return real(self, address)
    return guarded


def _guard_sendto(real):
    def guarded(self, data, *args):
        _check(args[-1])
        return real(self, data, *args)
    return guarded


def _guard_sendmsg(real):
    def guarded(self, buffers, *args):
        if len(args) >= 3:
            _check(args[2])
        return real(self, buffers, *args)
    return guarded


def _guard_host(real):
    def guarded(host, *args, **kwargs):
        if not _is_loopback(host):
            raise RuntimeError(f"network access is blocked in tests: {host!r}")
        return real(host, *args, **kwargs)
    return guarded


def _guard_first_address(real):
    def guarded(address, *args, **kwargs):
        _check(address)
        return real(address, *args, **kwargs)
    return guarded


def _patch(owner, name, wrap):
    if hasattr(owner, name):
        real = getattr(owner, name)
        _saved_attrs.append((owner, name, real))
        setattr(owner, name, wrap(real))


def pytest_configure(config):
    _patch(socket.socket, "connect", _guard_address)
    _patch(socket.socket, "connect_ex", _guard_address)
    _patch(socket.socket, "sendto", _guard_sendto)
    _patch(socket.socket, "sendmsg", _guard_sendmsg)
    for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
        _patch(socket, name, _guard_host)
    _patch(socket, "getnameinfo", _guard_first_address)
    _patch(socket, "create_connection", _guard_first_address)

    # The default Windows event loop connects without socket.connect.
    # The selector loop goes through the guarded functions above.
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    for name in CREDENTIAL_VARS:
        if name in os.environ:
            _saved_env[name] = os.environ.pop(name)
    for name, value in QUIET_TOOL_VARS.items():
        _saved_env.setdefault(name, os.environ.get(name))
        os.environ[name] = value


def pytest_unconfigure(config):
    while _saved_attrs:
        owner, name, real = _saved_attrs.pop()
        setattr(owner, name, real)
    for name, value in _saved_env.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
    _saved_env.clear()


@pytest.fixture(autouse=True)
def no_credentials(monkeypatch):
    """Keep credentials out even if an earlier test set one."""
    for name in CREDENTIAL_VARS:
        monkeypatch.delenv(name, raising=False)
