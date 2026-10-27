"""Shared test setup (B7): block the network and remove real credentials.

Everything is switched on in pytest_configure, before any test file is
imported, and stays on until the process exits, so exit handlers are covered
too. Loopback stays open, because local test servers and Windows socket
pairs need it. Proxy settings are cleared, so loopback cannot be used as a
way out through a local proxy.

Not covered here: DuckDB and dbt make their own network calls outside
Python sockets. DuckDB extension auto-install is turned off where the
connection is made (task T010). dbt usage stats are turned off below.
"""
import ipaddress
import os
import socket
import sys

import pytest

CREDENTIAL_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN")
QUIET_TOOL_VARS = {
    "DBT_SEND_ANONYMOUS_USAGE_STATS": "False",
    "DO_NOT_TRACK": "1",
    "NO_PROXY": "*",
    "no_proxy": "*",
}


def _is_loopback(host):
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    if host is None or host == "localhost":
        return True
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


def _guard_proactor_connect(real):
    def guarded(self, conn, address):
        _check(address)
        return real(self, conn, address)
    return guarded


def _guard_proactor_sendto(real):
    def guarded(self, conn, buf, flags=0, addr=None):
        _check(addr)
        return real(self, conn, buf, flags, addr)
    return guarded


def _patch(owner, name, wrap):
    if hasattr(owner, name):
        setattr(owner, name, wrap(getattr(owner, name)))


def pytest_configure(config):
    _patch(socket.socket, "connect", _guard_address)
    _patch(socket.socket, "connect_ex", _guard_address)
    _patch(socket.socket, "sendto", _guard_sendto)
    _patch(socket.socket, "sendmsg", _guard_sendmsg)
    for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
        _patch(socket, name, _guard_host)
    _patch(socket, "getnameinfo", _guard_first_address)
    _patch(socket, "create_connection", _guard_first_address)

    # The default Windows event loop connects through its own proactor,
    # not through socket.connect, so its methods are guarded too.
    if sys.platform == "win32":
        from asyncio import windows_events

        _patch(windows_events.IocpProactor, "connect", _guard_proactor_connect)
        _patch(windows_events.IocpProactor, "sendto", _guard_proactor_sendto)

    for name in list(os.environ):
        if name in CREDENTIAL_VARS or (name.lower().endswith("_proxy") and name.lower() != "no_proxy"):
            del os.environ[name]
    os.environ.update(QUIET_TOOL_VARS)


@pytest.fixture(autouse=True)
def no_credentials(monkeypatch):
    """Keep credentials out even if an earlier test set one."""
    for name in CREDENTIAL_VARS:
        monkeypatch.delenv(name, raising=False)
