"""B7: tests cannot reach the network, and never see a real credential.

Targets are reserved so they can never reach a real server: 192.0.2.1 and
2001:db8::1 are documentation addresses (RFC 5737, RFC 3849) and .invalid
names never resolve (RFC 2606). If the block were broken, a packet or a
lookup could still leave the machine. Connections use a short timeout. Name
lookups have no timeout parameter, so a broken block could make them wait
for the resolver.
"""
import asyncio
import os
import socket
import sys
import urllib.request

import pytest

pytest_plugins = ["pytester"]

OUTSIDE = ("192.0.2.1", 443)
OUTSIDE_V6 = ("2001:db8::1", 443, 0, 0)
BLOCKED = "network access is blocked"


def _tcp(family=socket.AF_INET):
    s = socket.socket(family, socket.SOCK_STREAM)
    s.settimeout(1)
    return s


# Outside connections are refused


def test_B7_a_socket_cannot_connect_outside():
    with _tcp() as s, pytest.raises(RuntimeError, match=BLOCKED):
        s.connect(OUTSIDE)


def test_B7_connect_ex_is_blocked_too():
    with _tcp() as s, pytest.raises(RuntimeError, match=BLOCKED):
        s.connect_ex(OUTSIDE)


def test_B7_an_ipv6_outside_address_is_blocked():
    try:
        s = _tcp(socket.AF_INET6)
    except OSError:
        pytest.skip("IPv6 sockets are not available here")
    with s, pytest.raises(RuntimeError, match=BLOCKED):
        s.connect(OUTSIDE_V6)


def test_B7_create_connection_is_blocked():
    with pytest.raises(RuntimeError, match=BLOCKED):
        socket.create_connection(OUTSIDE, timeout=1)


def test_B7_a_udp_packet_cannot_be_sent_outside():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        with pytest.raises(RuntimeError, match=BLOCKED):
            s.sendto(b"x", OUTSIDE)
        with pytest.raises(RuntimeError, match=BLOCKED):
            s.sendto(b"x", 0, OUTSIDE)


def test_B7_sendmsg_to_an_outside_address_is_blocked():
    if not hasattr(socket.socket, "sendmsg"):
        pytest.skip("sendmsg does not exist on this platform")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        with pytest.raises(RuntimeError, match=BLOCKED):
            s.sendmsg([b"x"], [], 0, OUTSIDE)


@pytest.mark.parametrize("lookup", [
    lambda: socket.getaddrinfo("blocked.invalid", 443),
    lambda: socket.gethostbyname("blocked.invalid"),
    lambda: socket.gethostbyname_ex("blocked.invalid"),
    lambda: socket.gethostbyaddr("192.0.2.1"),
    lambda: socket.getnameinfo(OUTSIDE, 0),
], ids=["getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr", "getnameinfo"])
def test_B7_every_name_lookup_is_blocked(lookup):
    with pytest.raises(RuntimeError, match=BLOCKED):
        lookup()


def test_B7_a_web_request_is_blocked():
    with pytest.raises(RuntimeError, match=BLOCKED):
        urllib.request.urlopen("http://192.0.2.1/", timeout=1)


def test_B7_proxy_settings_cannot_route_a_request_out(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("https_proxy", "http://127.0.0.1:9")
    # A fresh opener reads the proxy settings now. urlopen() reuses an old one.
    opener = urllib.request.build_opener()
    with pytest.raises(RuntimeError, match=BLOCKED):
        opener.open("https://192.0.2.1/", timeout=1)


def test_B7_proxy_variables_are_cleared_and_no_proxy_is_set():
    proxies = [n for n in os.environ if n.lower().endswith("_proxy") and n.lower() != "no_proxy"]
    assert proxies == []
    assert os.environ.get("NO_PROXY") == "*"
    assert os.environ.get("no_proxy") == "*"


def test_B7_an_asyncio_connection_is_blocked():
    # On Windows the default event loop connects without socket.connect.
    async def attempt():
        await asyncio.wait_for(asyncio.open_connection(*OUTSIDE), timeout=1)

    with pytest.raises(RuntimeError, match=BLOCKED):
        asyncio.run(attempt())


def test_B7_an_asyncio_datagram_to_outside_is_blocked():
    async def attempt():
        loop = asyncio.get_running_loop()
        await asyncio.wait_for(
            loop.create_datagram_endpoint(asyncio.DatagramProtocol, remote_addr=OUTSIDE), timeout=1)

    with pytest.raises(RuntimeError, match=BLOCKED):
        asyncio.run(attempt())


def test_B7_the_default_event_loop_is_kept_so_subprocesses_work():
    async def run_child():
        child = await asyncio.create_subprocess_exec(sys.executable, "-c", "pass")
        return await child.wait()

    assert asyncio.run(run_child()) == 0


# Loopback stays open, so local test servers work


@pytest.fixture
def local_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen()
    yield server.getsockname()
    server.close()


def test_B7_create_connection_to_loopback_works(local_server):
    socket.create_connection(local_server, timeout=1).close()


def test_B7_connect_ex_to_loopback_works(local_server):
    with _tcp() as s:
        assert s.connect_ex(local_server) == 0


def test_B7_localhost_still_resolves():
    assert socket.getaddrinfo("localhost", 80)
    assert socket.getaddrinfo(b"localhost", 80)  # anyio passes bytes


def test_B7_a_socket_pair_still_works():
    a, b = socket.socketpair()
    try:
        a.sendall(b"ok")
        assert b.recv(2) == b"ok"
    finally:
        a.close()
        b.close()


# The block and the key removal are active from the start of the run


def test_B7_no_credential_is_visible_and_the_block_is_on_at_import_time(pytester, monkeypatch):
    fake_key = "sk-" + "ant-" + "x" * 20  # built at run time, never one string
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"):
        monkeypatch.setenv(name, fake_key)
    pytester.makeconftest(_our_conftest())
    pytester.makepyfile(test_inner="""
        import os, socket
        SEEN = [n for n in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN") if n in os.environ]
        try:
            socket.create_connection(("192.0.2.1", 443), timeout=1)
            BLOCKED_AT_IMPORT = False
        except RuntimeError:
            BLOCKED_AT_IMPORT = True

        def test_inner():
            assert SEEN == []
            assert BLOCKED_AT_IMPORT
            assert "ANTHROPIC_API_KEY" not in os.environ
    """)
    result = pytester.runpytest_subprocess("-p", "no:cacheprovider")
    result.assert_outcomes(passed=1)


def test_B7_the_block_stays_on_until_the_process_exits(pytester, monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-" + "ant-" + "y" * 20)
    report = tmp_path / "at_exit.txt"
    pytester.makeconftest(_our_conftest())
    pytester.makepyfile(test_inner=f"""
        import atexit, os, socket

        def check_at_exit():
            try:
                socket.create_connection(("192.0.2.1", 443), timeout=1)
                blocked = "open"
            except RuntimeError:
                blocked = "blocked"
            key = "key" if "ANTHROPIC_API_KEY" in os.environ else "nokey"
            open({str(report)!r}, "w").write(blocked + " " + key)

        atexit.register(check_at_exit)

        def test_inner():
            pass
    """)
    pytester.runpytest_subprocess("-p", "no:cacheprovider").assert_outcomes(passed=1)
    assert report.read_text() == "blocked nokey"


def _our_conftest():
    with open(os.path.join(os.path.dirname(__file__), "conftest.py"), encoding="utf-8") as f:
        return f.read()


def test_B7_dbt_usage_stats_are_off():
    assert os.environ.get("DBT_SEND_ANONYMOUS_USAGE_STATS") == "False"
    assert os.environ.get("DO_NOT_TRACK") == "1"
