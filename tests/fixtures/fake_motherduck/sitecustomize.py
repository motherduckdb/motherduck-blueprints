"""Refuse connections to MotherDuck and GitHub in every process that loads the fake runtime.

Python imports sitecustomize from PYTHONPATH at startup, so the CLI under test cannot reach a
live account or the GitHub API even if a code path forgets a guard. Package indexes stay
reachable because scripts/mock-test.sh installs scaffold copies with pip.
"""
import socket

_BLOCKED_DOMAINS = ("motherduck.com", "github.com", "githubusercontent.com")
_getaddrinfo = socket.getaddrinfo


def _guarded(host, *args, **kwargs):  # type: ignore[no-untyped-def]
    name = (host.decode() if isinstance(host, bytes) else str(host or "")).lower().rstrip(".")
    if any(name == domain or name.endswith("." + domain) for domain in _BLOCKED_DOMAINS):
        raise socket.gaierror(f"md-blueprints tests never contact {name}")
    return _getaddrinfo(host, *args, **kwargs)


socket.getaddrinfo = _guarded
