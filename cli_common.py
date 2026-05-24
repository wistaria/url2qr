from __future__ import annotations

import os
import sys


def require_env(name: str) -> str | None:
    value = os.getenv(name)
    if not value:
        print(f"Error: {name} is not set", file=sys.stderr)
        return None
    return value


def select_qr_text(qr_target: str, short_url: str, public_url: str) -> str:
    return short_url if qr_target == "short" else public_url
