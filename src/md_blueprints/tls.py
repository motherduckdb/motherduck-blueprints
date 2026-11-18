"""TLS settings for HTTPS requests that md-blueprints makes from the user's machine."""
from __future__ import annotations

import os
import ssl

import certifi


def ssl_context() -> ssl.SSLContext:
    """A verifying context that does not depend on how Python was installed.

    python.org builds for macOS bundle their own OpenSSL, ignore the keychain, and have no CA bundle
    until "Install Certificates.command" runs, so plain urlopen fails verification. certifi supplies
    the bundle instead. SSL_CERT_FILE, when it names a file, takes precedence for networks that
    inspect TLS with their own certificate authority.
    """
    override = os.environ.get("SSL_CERT_FILE", "").strip()
    cafile = override if override and os.path.isfile(override) else certifi.where()
    return ssl.create_default_context(cafile=cafile)
