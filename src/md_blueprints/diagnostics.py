from __future__ import annotations

import html
import os
import sys
from pathlib import Path


def report_error(error: Exception) -> None:
    message = str(error)
    for key, value in os.environ.items():
        if value and any(part in key.upper() for part in ("TOKEN", "PASSWORD", "SECRET", "API_KEY")):
            message = message.replace(value, "[redacted]")
    lower = message.lower()
    if "environment" in lower and "next:" not in lower:
        message += (
            "\nNext: check targets in motherduck.yml. The environment name must match GitHub Settings > "
            "Environments and the workflow job's environment. Set deployment.identity to the service account "
            "and deployment.tokenEnvVar to MOTHERDUCK_TOKEN."
        )
    if any(text in lower for text in ("permission denied", "access denied", "insufficient privilege", "not authorized")):
        message += (
            "\nNext: check the service account's permissions on the required databases. "
            "For custom roles or organization-wide Guides, use an admin deployment identity."
        )
    elif any(text in lower for text in ("invalid token", "expired token", "authentication failed", "unauthorized")):
        message += (
            "\nNext: replace MOTHERDUCK_TOKEN in the job's GitHub Environment with a valid "
            "service-account read/write token, then rerun the failed job."
        )
    print(f"Error: {message}", file=sys.stderr)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        try:
            with Path(summary).open("a", encoding="utf-8") as handle:
                handle.write(f"### Blueprints needs attention\n\n<pre>{html.escape(message)}</pre>\n\n")
        except OSError:
            print("Could not write the GitHub Actions summary; see the error above.", file=sys.stderr)
