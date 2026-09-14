"""Seals the demo process off from the network and from the order path.

Two refusals, both enforced in the server process rather than by hiding
buttons:

1. **No outbound network.** Every Python socket connection to a non-loopback
   address raises ``DemoRefused``, and so does name resolution -- except the
   single mail server ``allow_outbound`` names, which sends sign-in codes. ``yfinance``
   is replaced by a stub whose every attribute raises, because its transport
   (``curl_cffi``) is C code that never goes through Python's ``socket``.
   The data the demo shows comes from ``demo/fixtures/`` and nowhere else.

2. **No broker, no paper-trading agent, no live mode.** Importing
   ``lib.live`` (the Interactive Brokers runner, broker and guards) or the IB
   client libraries raises ``DemoRefused``. The demo image does not install
   ``ib_async`` at all; this is the second lock on the same door, and it is
   what the tests exercise.
"""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import ipaddress
import socket
import sys
import types
from typing import Any

# Modules that can place, route or supervise an order. The dashboard imports
# none of them; only the `sfa run|status|kill` CLI does, lazily.
BLOCKED_MODULE_PREFIXES = ("lib.live", "ib_async", "ib_insync", "ibapi")


class DemoRefused(Exception):
    """Base for anything the public demo is not allowed to do."""


class BrokerRefused(DemoRefused, ImportError):
    """A module on the order path was imported. Fails like a missing package."""


class NetworkRefused(DemoRefused, ConnectionRefusedError):
    """An outbound connection was attempted. Code that already copes with a
    refused connection copes with this too."""


# --------------------------------------------------------------------------- broker


class _BrokerBlocker(importlib.abc.MetaPathFinder):
    """Refuses every module on the order path."""

    def find_spec(self, fullname: str, path: Any = None, target: Any = None):  # noqa: D401
        for prefix in BLOCKED_MODULE_PREFIXES:
            if fullname == prefix or fullname.startswith(prefix + "."):
                raise BrokerRefused(
                    f"{fullname} is disabled in the public demo: no broker connection, "
                    "no paper-trading agent and no live mode run here."
                )
        return None


_BROKER_BLOCKER = _BrokerBlocker()


def install_broker_seal() -> None:
    if _BROKER_BLOCKER not in sys.meta_path:
        sys.meta_path.insert(0, _BROKER_BLOCKER)
    # Anything imported before the seal went up is evicted, so the next import
    # goes through the blocker instead of the module cache.
    for name in list(sys.modules):
        if any(name == p or name.startswith(p + ".") for p in BLOCKED_MODULE_PREFIXES):
            del sys.modules[name]


def remove_broker_seal() -> None:
    """Tests only."""
    while _BROKER_BLOCKER in sys.meta_path:
        sys.meta_path.remove(_BROKER_BLOCKER)


# --------------------------------------------------------------------------- network

_ORIGINAL = {
    "connect": socket.socket.connect,
    "connect_ex": socket.socket.connect_ex,
    "getaddrinfo": socket.getaddrinfo,
    "create_connection": socket.create_connection,
}


def _is_local(host: Any) -> bool:
    """Loopback, or the unspecified address a server binds to (0.0.0.0, ::)."""
    if host is None:
        return False
    text = host.decode() if isinstance(host, bytes) else str(host)
    if text in ("localhost", ""):
        return True
    try:
        address = ipaddress.ip_address(text.split("%", 1)[0])
    except ValueError:
        return False
    return address.is_loopback or address.is_unspecified


def _address_host(address: Any) -> Any:
    if isinstance(address, tuple) and address:
        return address[0]
    return None  # AF_UNIX paths and the like carry no host


# The one door the seal can open: the mail server that sends sign-in codes
# (demo.access.mailer). A host:port is allowed by name, and the addresses that
# name resolves to are allowed as they come back from the lookup -- so the
# connection can reach that server and nothing else on the same machine.
_ALLOWED_HOSTS: set[tuple[str, int]] = set()
_ALLOWED_ADDRESSES: set[tuple[str, int]] = set()


def allow_outbound(host: str, port: int) -> None:
    """Let the demo process connect to ``host:port`` (and to nothing else new)."""
    _ALLOWED_HOSTS.add((host.strip().lower(), int(port)))


def _port(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _host_allowed(host: Any, port: Any) -> bool:
    if host is None:
        return False
    text = (host.decode() if isinstance(host, bytes) else str(host)).lower()
    return (text, _port(port)) in _ALLOWED_HOSTS


def _address_allowed(address: Any) -> bool:
    if not (isinstance(address, tuple) and len(address) >= 2):
        return False
    return (str(address[0]), _port(address[1])) in _ALLOWED_ADDRESSES


def _refuse(host: Any) -> NetworkRefused:
    return NetworkRefused(
        f"Outbound network to {host!r} is disabled in the public demo; "
        "it reads a frozen snapshot and never calls a market-data API."
    )


def _sealed_connect(self: socket.socket, address: Any):
    host = _address_host(address)
    if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_local(host) and not _address_allowed(address):
        raise _refuse(host)
    return _ORIGINAL["connect"](self, address)


def _sealed_connect_ex(self: socket.socket, address: Any):
    host = _address_host(address)
    if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_local(host) and not _address_allowed(address):
        raise _refuse(host)
    return _ORIGINAL["connect_ex"](self, address)


def _sealed_getaddrinfo(host: Any, *args: Any, **kwargs: Any):
    # host=None is a passive lookup for binding a listening socket.
    if host is None or _is_local(host):
        return _ORIGINAL["getaddrinfo"](host, *args, **kwargs)
    port = args[0] if args else kwargs.get("port")
    if not _host_allowed(host, port):
        raise _refuse(host)
    results = _ORIGINAL["getaddrinfo"](host, *args, **kwargs)
    for *_ignored, sockaddr in results:
        _ALLOWED_ADDRESSES.add((str(sockaddr[0]), _port(sockaddr[1])))
    return results


def _sealed_create_connection(address: Any, *args: Any, **kwargs: Any):
    host = _address_host(address)
    if not _is_local(host) and not _host_allowed(host, address[1] if len(address) > 1 else None):
        raise _refuse(host)
    return _ORIGINAL["create_connection"](address, *args, **kwargs)


class _SealedYFinance(types.ModuleType):
    """Stands in for ``yfinance``: importable, unusable."""

    def __getattr__(self, name: str):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        raise NetworkRefused(
            f"yfinance.{name} is disabled in the public demo; prices and fundamentals "
            "come from the frozen snapshot in demo/fixtures/."
        )


def install_network_seal() -> None:
    socket.socket.connect = _sealed_connect  # type: ignore[method-assign]
    socket.socket.connect_ex = _sealed_connect_ex  # type: ignore[method-assign]
    socket.getaddrinfo = _sealed_getaddrinfo  # type: ignore[assignment]
    socket.create_connection = _sealed_create_connection  # type: ignore[assignment]

    stub = _SealedYFinance("yfinance")
    stub.__spec__ = importlib.machinery.ModuleSpec("yfinance", None)
    stub.__file__ = "<sealed by demo.sealing>"
    sys.modules["yfinance"] = stub
    # Modules that already bound `yf` keep a reference to the real package;
    # point them at the stub too.
    for module in list(sys.modules.values()):
        if isinstance(module, types.ModuleType) and getattr(module, "__name__", "").startswith(("lib.", "scripts.")):
            for attr in ("yf", "yfinance"):
                if attr in vars(module) and vars(module)[attr] is not stub:
                    setattr(module, attr, stub)


def remove_network_seal(real_yfinance: types.ModuleType | None = None) -> None:
    """Tests only."""
    socket.socket.connect = _ORIGINAL["connect"]  # type: ignore[method-assign]
    socket.socket.connect_ex = _ORIGINAL["connect_ex"]  # type: ignore[method-assign]
    socket.getaddrinfo = _ORIGINAL["getaddrinfo"]  # type: ignore[assignment]
    socket.create_connection = _ORIGINAL["create_connection"]  # type: ignore[assignment]
    _ALLOWED_HOSTS.clear()
    _ALLOWED_ADDRESSES.clear()
    if real_yfinance is not None:
        sys.modules["yfinance"] = real_yfinance
        for module in list(sys.modules.values()):
            if isinstance(module, types.ModuleType) and getattr(module, "__name__", "").startswith(("lib.", "scripts.")):
                for attr in ("yf", "yfinance"):
                    if isinstance(vars(module).get(attr), _SealedYFinance):
                        setattr(module, attr, real_yfinance)
