from __future__ import annotations

import ssl
from pathlib import Path

import certifi
import pytest

from md_blueprints import tls


def capture_cafile(monkeypatch: pytest.MonkeyPatch) -> list[str | None]:
    seen: list[str | None] = []
    create = ssl.create_default_context

    def recording(*args: object, cafile: str | None = None, **kwargs: object) -> ssl.SSLContext:
        seen.append(cafile)
        return create(cafile=cafile)

    monkeypatch.setattr(ssl, "create_default_context", recording)
    return seen


def test_ssl_context_uses_certifi_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    seen = capture_cafile(monkeypatch)
    context = tls.ssl_context()
    assert seen == [certifi.where()]
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert context.get_ca_certs()


def test_ssl_context_prefers_an_existing_ssl_cert_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bundle = tmp_path / "corporate.pem"
    bundle.write_text(Path(certifi.where()).read_text())
    monkeypatch.setenv("SSL_CERT_FILE", str(bundle))
    seen = capture_cafile(monkeypatch)
    context = tls.ssl_context()
    assert seen == [str(bundle)]
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True


def test_ssl_context_ignores_a_missing_ssl_cert_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SSL_CERT_FILE", str(tmp_path / "missing.pem"))
    seen = capture_cafile(monkeypatch)
    tls.ssl_context()
    assert seen == [certifi.where()]
