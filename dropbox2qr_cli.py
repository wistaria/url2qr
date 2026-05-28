#!/usr/bin/env python3
from __future__ import annotations

if __name__ == "__main__":
    from cli_common import ensure_project_venv

    ensure_project_venv()

import argparse
import base64
import hashlib
import json
import re
import secrets
import sys
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from cli_common import (
    acquire_bitly_token,
    config_path,
    load_cached_fields,
    make_qr,
    parse_args_or_show_help,
    prompt_oauth_credentials,
    prompt_optional_secret,
    save_cached_fields,
    select_qr_text,
    shorten_with_bitly,
)


# ---------------------------------------------------------------------------
# Dropbox OAuth 2.0 + PKCE
# ---------------------------------------------------------------------------

_DROPBOX_CREDENTIALS_CACHE = config_path("dropbox_credentials.json")
_DROPBOX_TOKEN_CACHE = config_path("dropbox_tokens.json")
_DROPBOX_AUTH_URL = "https://www.dropbox.com/oauth2/authorize"
_DROPBOX_TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"
_DEFAULT_REDIRECT_PORT = 8080
_AUTH_TIMEOUT = 120


def acquire_dropbox_token(
    redirect_port: int = _DEFAULT_REDIRECT_PORT,
    no_browser: bool = False,
) -> str | None:
    cached = _load_dropbox_tokens()
    if cached:
        expires_at = cached.get("expires_at")
        if not expires_at or (
            isinstance(expires_at, (int, float)) and expires_at > time.time()
        ):
            return str(cached["access_token"])

    credentials = load_cached_fields(
        _DROPBOX_CREDENTIALS_CACHE, ("client_id", "client_secret")
    )
    if not credentials:
        token = prompt_optional_secret("Dropbox access token (leave empty for OAuth): ")
        if token:
            _save_dropbox_tokens({"access_token": token, "source": "manual"})
            return token
        credentials = prompt_oauth_credentials(
            "Dropbox",
            _DROPBOX_CREDENTIALS_CACHE,
            client_id_label="App key",
            client_secret_label="App secret",
        )

    return get_dropbox_access_token(
        str(credentials["client_id"]),
        str(credentials["client_secret"]),
        redirect_port,
        no_browser,
    )


def get_dropbox_access_token(
    client_id: str,
    client_secret: str,
    redirect_port: int = _DEFAULT_REDIRECT_PORT,
    no_browser: bool = False,
) -> str:
    cached = _load_dropbox_tokens()
    if cached:
        expires_at = cached.get("expires_at", 0)
        if isinstance(expires_at, (int, float)) and expires_at > time.time():
            return str(cached["access_token"])
        refresh_token = cached.get("refresh_token")
        if refresh_token:
            try:
                tokens = _refresh_dropbox_tokens(
                    client_id, client_secret, str(refresh_token)
                )
                return str(tokens["access_token"])
            except requests.RequestException:
                pass
    tokens = _authorize_dropbox(client_id, client_secret, redirect_port, no_browser)
    return str(tokens["access_token"])


def _load_dropbox_tokens() -> dict | None:
    if not _DROPBOX_TOKEN_CACHE.exists():
        return None
    try:
        data = json.loads(_DROPBOX_TOKEN_CACHE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and "access_token" in data else None
    except (json.JSONDecodeError, OSError):
        return None


def _save_dropbox_tokens(tokens: dict) -> None:
    save_cached_fields(_DROPBOX_TOKEN_CACHE, tokens)


def _store_with_expiry(tokens: dict) -> dict:
    tokens["expires_at"] = time.time() + tokens.get("expires_in", 14400) - 60
    _save_dropbox_tokens(tokens)
    return tokens


def _refresh_dropbox_tokens(
    client_id: str, client_secret: str, refresh_token: str
) -> dict:
    res = requests.post(
        _DROPBOX_TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=15,
    )
    res.raise_for_status()
    tokens = res.json()
    # Dropbox does not return a new refresh_token on refresh — preserve the original.
    if "refresh_token" not in tokens:
        tokens["refresh_token"] = refresh_token
    return _store_with_expiry(tokens)


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return verifier, challenge


def _authorize_dropbox(
    client_id: str,
    client_secret: str,
    redirect_port: int,
    no_browser: bool,
) -> dict:
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)
    redirect_uri = f"http://localhost:{redirect_port}/callback"
    auth_url = (
        _DROPBOX_AUTH_URL
        + "?"
        + urlencode(
            {
                "client_id": client_id,
                "response_type": "code",
                "redirect_uri": redirect_uri,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "token_access_type": "offline",
            }
        )
    )

    if no_browser:
        code = _get_code_no_browser(auth_url, state)
    else:
        code = _get_code_via_browser(auth_url, state, redirect_port)

    res = requests.post(
        _DROPBOX_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
            "code_verifier": verifier,
        },
        timeout=15,
    )
    res.raise_for_status()
    return _store_with_expiry(res.json())


def _get_code_no_browser(auth_url: str, expected_state: str) -> str:
    print("Open the following URL in a browser to authorize Dropbox:")
    print(f"  {auth_url}")
    print()
    print("After authorizing, your browser will redirect to localhost and show")
    print(
        "a connection error. Copy the full URL from the address bar and paste it here."
    )
    print()
    callback_url = input("Callback URL: ").strip()
    parsed = urlparse(callback_url)
    qs = parse_qs(parsed.query)
    if "code" not in qs:
        raise ValueError("No authorization code found in the callback URL.")
    if qs.get("state", [""])[0] != expected_state:
        raise ValueError("OAuth state mismatch — possible CSRF. Authorization aborted.")
    return qs["code"][0]


def _get_code_via_browser(
    auth_url: str, expected_state: str, redirect_port: int
) -> str:
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

    print("Opening browser for Dropbox authorization...")
    print(f"If the browser does not open, visit:\n  {auth_url}")
    webbrowser.open(auth_url)

    deadline = time.time() + _AUTH_TIMEOUT
    while "code" not in result and time.time() < deadline:
        server.handle_request()
    server.server_close()

    if "code" not in result:
        raise TimeoutError(
            f"Dropbox authorization timed out after {_AUTH_TIMEOUT}s. "
            "Please re-run the command to try again."
        )
    if result.get("state") != expected_state:
        raise ValueError("OAuth state mismatch — possible CSRF. Authorization aborted.")
    return result["code"]


# ---------------------------------------------------------------------------
# Dropbox API
# ---------------------------------------------------------------------------


def normalize_dropbox_path(path: str) -> str:
    stripped = path.strip()
    if not stripped:
        raise ValueError("Dropbox path must not be empty")

    unix_like = stripped.replace("\\", "/")

    # Convert local Dropbox paths into Dropbox API paths.
    # Examples:
    # - /Users/me/Library/CloudStorage/Dropbox/MyFolder/file.txt
    # - /Users/me/Library/CloudStorage/Dropbox (Personal)/MyFolder/file.txt
    # - /Users/me/Dropbox/MyFolder/file.txt
    local_patterns = [
        r"/CloudStorage/Dropbox(?:\s\([^/]+\))?(/.*)?$",
        r"/Dropbox(?:\s\([^/]+\))?(/.*)?$",
    ]
    for pattern in local_patterns:
        match = re.search(pattern, unix_like)
        if match:
            suffix = match.group(1) or "/"
            return _normalize_dropbox_api_path(suffix)

    # Dropbox API paths always start with '/'.
    if unix_like.startswith("/"):
        return _normalize_dropbox_api_path(unix_like)

    return _normalize_dropbox_api_path(unix_like)


def _normalize_dropbox_api_path(path: str) -> str:
    api_path = path if path.startswith("/") else f"/{path}"
    if api_path != "/":
        api_path = api_path.rstrip("/")
    return api_path


def _post_dropbox_api(endpoint: str, token: str, payload: dict) -> requests.Response:
    res = requests.post(
        f"https://api.dropboxapi.com/2/{endpoint}",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=15,
    )
    return res


def _dropbox_error_summary(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        preview = response.text.strip().replace("\n", " ")
        if len(preview) > 200:
            preview = preview[:200] + "..."
        if preview:
            return f"status={response.status_code}, body={preview}"
        return f"status={response.status_code}"

    if not isinstance(payload, dict):
        preview = str(payload)
        if len(preview) > 200:
            preview = preview[:200] + "..."
        return f"status={response.status_code}, body={preview}"

    summary = payload.get("error_summary")
    if summary:
        return f"status={response.status_code}, error_summary={summary}"
    return f"status={response.status_code}, body={payload}"


def _extract_missing_scopes(*messages: str) -> list[str]:
    found: set[str] = set()
    for message in messages:
        for scope in re.findall(r"required scope '([^']+)'", message):
            found.add(scope)
    return sorted(found)


def _has_missing_scope_error(*messages: str) -> bool:
    return any("missing_scope/" in message for message in messages)


def get_or_create_shared_url(dropbox_path: str, token: str) -> str:
    create_res = _post_dropbox_api(
        "sharing/create_shared_link_with_settings",
        token,
        {"path": dropbox_path},
    )

    if create_res.ok:
        return create_res.json()["url"]

    # Try listing existing links even if create fails; some environments disallow
    # creation but still allow reading existing shared links.
    list_res = _post_dropbox_api(
        "sharing/list_shared_links",
        token,
        {"path": dropbox_path, "direct_only": True},
    )
    if list_res.ok:
        links = list_res.json().get("links", [])
        if links:
            return links[0]["url"]

    create_msg = _dropbox_error_summary(create_res)
    list_msg = _dropbox_error_summary(list_res)
    missing_scopes = _extract_missing_scopes(create_msg, list_msg)
    scope_hint = ""
    if missing_scopes:
        joined = ", ".join(missing_scopes)
        scope_hint = (
            " Required Dropbox app scopes are missing: "
            f"{joined}. Update app permissions in Dropbox App Console, then "
            "generate a new access token or delete the cached tokens and re-authorize."
        )
    elif _has_missing_scope_error(create_msg, list_msg):
        scope_hint = (
            " Dropbox token is missing required app scopes. "
            "Enable at least sharing.read and sharing.write in Dropbox App Console, "
            "then generate a new access token or delete the cached tokens and re-authorize."
        )
    raise ValueError(
        "Dropbox API did not return a shared URL "
        f"(create_shared_link_with_settings: {create_msg}; "
        f"list_shared_links: {list_msg}).{scope_hint}"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create a Dropbox shared URL, then generate a QR code and optional "
            "Bitly URL."
        )
    )
    parser.add_argument("path", help="Dropbox path (API path or local Dropbox path)")
    parser.add_argument(
        "-o", "--output", default="qrcode.png", help="QR code output file"
    )
    parser.add_argument(
        "--qr-target",
        choices=["short", "public"],
        default="public",
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
        help="Skip Bitly URL shortening even if a Bitly token is cached",
    )
    parser.add_argument(
        "--bitly",
        action="store_true",
        help="Configure Bitly credentials if no Bitly token is cached",
    )

    args = parse_args_or_show_help(parser, argv)
    if args is None:
        return 2

    try:
        dropbox_token = acquire_dropbox_token(args.redirect_port, args.no_browser)
    except (TimeoutError, ValueError, requests.RequestException) as exc:
        print(f"Error: Dropbox authentication failed: {exc}", file=sys.stderr)
        return 1
    if not dropbox_token:
        return 1

    try:
        dropbox_path = normalize_dropbox_path(args.path)
    except ValueError as exc:
        print(f"Error: Invalid Dropbox path: {exc}", file=sys.stderr)
        return 1

    try:
        public_url = get_or_create_shared_url(dropbox_path, dropbox_token)
    except (requests.RequestException, KeyError, ValueError) as exc:
        print(f"Error: Failed to get Dropbox shared URL: {exc}", file=sys.stderr)
        return 1

    bitly_url = None
    bitly_token = None
    if not args.no_bitly:
        try:
            bitly_token = acquire_bitly_token(
                args.redirect_port, args.no_browser, configure=args.bitly
            )
        except (TimeoutError, ValueError, requests.RequestException) as exc:
            print(f"Error: Bitly authentication failed: {exc}", file=sys.stderr)
            return 1
    if bitly_token:
        try:
            bitly_url = shorten_with_bitly(public_url, bitly_token)
        except (requests.RequestException, KeyError, ValueError) as exc:
            print(f"Error: Failed to shorten URL with Bitly: {exc}", file=sys.stderr)
            return 1

    qr_text = select_qr_text(args.qr_target, bitly_url, public_url)
    try:
        make_qr(qr_text, args.output)
    except OSError as exc:
        print(f"Error: Failed to save QR code image: {exc}", file=sys.stderr)
        return 1

    print(f"Dropbox path: {dropbox_path}")
    print(f"Public URL:   {public_url}")
    if bitly_url:
        print(f"Bitly URL:    {bitly_url}")
    print(f"QR code:      {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
