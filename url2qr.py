#!/usr/bin/env python3
from __future__ import annotations

if __name__ == "__main__":
    from cli_common import ensure_project_venv

    ensure_project_venv()

import argparse
import json
import os
import secrets
import sys
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import qrcode
import requests

from cli_common import parse_args_or_show_help, select_qr_text


# ---------------------------------------------------------------------------
# Bitly OAuth 2.0
# ---------------------------------------------------------------------------

_BITLY_TOKEN_CACHE = Path.home() / ".config" / "url2qr" / "bitly_tokens.json"
_BITLY_AUTH_URL = "https://bitly.com/oauth/authorize"
_BITLY_TOKEN_URL = "https://api-ssl.bitly.com/oauth/access_token"
_DEFAULT_REDIRECT_PORT = 8080
_AUTH_TIMEOUT = 120


def acquire_bitly_token(
    redirect_port: int = _DEFAULT_REDIRECT_PORT,
    no_browser: bool = False,
) -> str | None:
    static = os.environ.get("BITLY_ACCESS_TOKEN")
    if static:
        return static
    client_id = os.environ.get("BITLY_CLIENT_ID")
    client_secret = os.environ.get("BITLY_CLIENT_SECRET")
    if not client_id or not client_secret:
        print(
            "Warning: Bitly not configured; skipping URL shortening. "
            "Set BITLY_ACCESS_TOKEN or both BITLY_CLIENT_ID and BITLY_CLIENT_SECRET.",
            file=sys.stderr,
        )
        return None
    return get_bitly_access_token(client_id, client_secret, redirect_port, no_browser)


def get_bitly_access_token(
    client_id: str,
    client_secret: str,
    redirect_port: int = _DEFAULT_REDIRECT_PORT,
    no_browser: bool = False,
) -> str:
    cached = _load_bitly_tokens()
    if cached:
        return str(cached["access_token"])
    tokens = _authorize_bitly(client_id, client_secret, redirect_port, no_browser)
    return str(tokens["access_token"])


def _load_bitly_tokens() -> dict | None:
    if not _BITLY_TOKEN_CACHE.exists():
        return None
    try:
        data = json.loads(_BITLY_TOKEN_CACHE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and "access_token" in data else None
    except (json.JSONDecodeError, OSError):
        return None


def _save_bitly_tokens(tokens: dict) -> None:
    _BITLY_TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
    _BITLY_TOKEN_CACHE.write_text(json.dumps(tokens, indent=2), encoding="utf-8")
    _BITLY_TOKEN_CACHE.chmod(0o600)


def _authorize_bitly(
    client_id: str,
    client_secret: str,
    redirect_port: int,
    no_browser: bool,
) -> dict:
    state = secrets.token_urlsafe(16)
    redirect_uri = f"http://localhost:{redirect_port}/callback"
    auth_url = (
        _BITLY_AUTH_URL
        + "?"
        + urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "state": state,
            }
        )
    )

    if no_browser:
        code = _get_code_no_browser(auth_url, state)
    else:
        code = _get_code_via_browser(auth_url, state, redirect_port)

    res = requests.post(
        _BITLY_TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        },
        timeout=15,
    )
    res.raise_for_status()
    tokens = res.json()
    _save_bitly_tokens(tokens)
    return tokens


def _get_code_no_browser(auth_url: str, expected_state: str) -> str:
    print("Open the following URL in a browser to authorize Bitly:")
    print(f"  {auth_url}")
    print()
    print("After authorizing, your browser will redirect to localhost and show")
    print("a connection error. Copy the full URL from the address bar and paste it here.")
    print()
    callback_url = input("Callback URL: ").strip()
    parsed = urlparse(callback_url)
    qs = parse_qs(parsed.query)
    if "code" not in qs:
        raise ValueError("No authorization code found in the callback URL.")
    if qs.get("state", [""])[0] != expected_state:
        raise ValueError("OAuth state mismatch — possible CSRF. Authorization aborted.")
    return qs["code"][0]


def _get_code_via_browser(auth_url: str, expected_state: str, redirect_port: int) -> str:
    result: dict[str, str] = {}

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/callback":
                qs = parse_qs(parsed.query)
                if "code" in qs:
                    result["code"] = qs["code"][0]
                    result["state"] = qs.get("state", [""])[0]
                body = b"<html><body><h2>Authorized. You can close this window.</h2></body></html>"
            else:
                body = b"<html><body><h2>Not found.</h2></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_: object) -> None:
            pass

    server = HTTPServer(("localhost", redirect_port), _Handler)
    server.timeout = 1

    print("Opening browser for Bitly authorization...")
    print(f"If the browser does not open, visit:\n  {auth_url}")
    webbrowser.open(auth_url)

    deadline = time.time() + _AUTH_TIMEOUT
    while "code" not in result and time.time() < deadline:
        server.handle_request()
    server.server_close()

    if "code" not in result:
        raise TimeoutError(
            f"Bitly authorization timed out after {_AUTH_TIMEOUT}s. "
            "Please re-run the command to try again."
        )
    if result.get("state") != expected_state:
        raise ValueError("OAuth state mismatch — possible CSRF. Authorization aborted.")
    return result["code"]


# ---------------------------------------------------------------------------
# Bitly shorten + QR
# ---------------------------------------------------------------------------


def shorten_with_bitly(url: str, token: str) -> str:
    res = requests.post(
        "https://api-ssl.bitly.com/v4/shorten",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "long_url": url,
            "domain": "bit.ly",
        },
        timeout=10,
    )
    res.raise_for_status()
    return res.json()["link"]


def make_qr(text: str, output: str) -> None:
    img = qrcode.make(text)
    img.save(output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a QR code from a URL, optionally with a Bitly URL."
    )
    parser.add_argument("url", help="Original URL")
    parser.add_argument(
        "-o", "--output", default="qrcode.png", help="QR code output file"
    )
    parser.add_argument(
        "--qr-target",
        choices=["short", "original"],
        default="original",
        help="Which URL to encode in the QR code; short means Bitly when available",
    )
    parser.add_argument(
        "--redirect-port",
        type=int,
        default=_DEFAULT_REDIRECT_PORT,
        help=f"Local port for OAuth callback (default: {_DEFAULT_REDIRECT_PORT})",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help=(
            "Print the authorization URL and prompt for the callback URL "
            "instead of opening a browser (useful for headless environments)"
        ),
    )
    parser.add_argument(
        "--no-bitly",
        action="store_true",
        help="Skip Bitly URL shortening even if credentials are configured",
    )

    args = parse_args_or_show_help(parser, argv)
    if args is None:
        return 2

    bitly_url = None
    token = None
    if not args.no_bitly:
        try:
            token = acquire_bitly_token(args.redirect_port, args.no_browser)
        except (TimeoutError, ValueError, requests.RequestException) as exc:
            print(f"Error: Bitly authentication failed: {exc}", file=sys.stderr)
            return 1

    if token:
        try:
            bitly_url = shorten_with_bitly(args.url, token)
        except (requests.RequestException, KeyError, ValueError) as exc:
            print(f"Error: Failed to shorten URL with Bitly: {exc}", file=sys.stderr)
            return 1

    qr_text = select_qr_text(args.qr_target, bitly_url, args.url)
    try:
        make_qr(qr_text, args.output)
    except OSError as exc:
        print(f"Error: Failed to save QR code image: {exc}", file=sys.stderr)
        return 1

    print(f"Original URL: {args.url}")
    if bitly_url:
        print(f"Bitly URL:    {bitly_url}")
    print(f"QR code:      {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
