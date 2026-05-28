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
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from cli_common import (
    acquire_bitly_token,
    make_qr,
    parse_args_or_show_help,
    require_env,
    select_qr_text,
    shorten_with_bitly,
)

# ---------------------------------------------------------------------------
# OAuth 2.0 + PKCE
# ---------------------------------------------------------------------------

_TOKEN_CACHE = Path.home() / ".config" / "url2qr" / "box_tokens.json"
_AUTH_URL = "https://account.box.com/api/oauth2/authorize"
_TOKEN_URL = "https://api.box.com/oauth2/token"
_DEFAULT_REDIRECT_PORT = 8080
_AUTH_TIMEOUT = 120


def get_box_access_token(
    client_id: str,
    client_secret: str,
    redirect_port: int = _DEFAULT_REDIRECT_PORT,
) -> str:
    cached = _load_tokens()
    if cached:
        expires_at = cached.get("expires_at", 0)
        if isinstance(expires_at, (int, float)) and expires_at > time.time():
            return str(cached["access_token"])
        refresh_token = cached.get("refresh_token")
        if refresh_token:
            try:
                tokens = _refresh_tokens(client_id, client_secret, str(refresh_token))
                return str(tokens["access_token"])
            except requests.RequestException:
                pass

    tokens = _authorize(client_id, client_secret, redirect_port)
    return str(tokens["access_token"])


def _load_tokens() -> dict | None:
    if not _TOKEN_CACHE.exists():
        return None
    try:
        data = json.loads(_TOKEN_CACHE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def _save_tokens(tokens: dict) -> None:
    _TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
    _TOKEN_CACHE.write_text(json.dumps(tokens, indent=2), encoding="utf-8")
    _TOKEN_CACHE.chmod(0o600)


def _store_with_expiry(tokens: dict) -> dict:
    tokens["expires_at"] = time.time() + tokens.get("expires_in", 3600) - 60
    _save_tokens(tokens)
    return tokens


def _refresh_tokens(client_id: str, client_secret: str, refresh_token: str) -> dict:
    res = requests.post(
        _TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=15,
    )
    res.raise_for_status()
    return _store_with_expiry(res.json())


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return verifier, challenge


def _authorize(client_id: str, client_secret: str, redirect_port: int) -> dict:
    verifier, challenge = _pkce_pair()
    redirect_uri = f"http://localhost:{redirect_port}/callback"
    state = secrets.token_urlsafe(16)

    auth_url = (
        _AUTH_URL
        + "?"
        + urlencode(
            {
                "client_id": client_id,
                "response_type": "code",
                "redirect_uri": redirect_uri,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
    )

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

    print("Opening browser for Box authorization...")
    print(f"If the browser does not open, visit:\n  {auth_url}")
    webbrowser.open(auth_url)

    deadline = time.time() + _AUTH_TIMEOUT
    while "code" not in result and time.time() < deadline:
        server.handle_request()
    server.server_close()

    if "code" not in result:
        raise TimeoutError(
            f"Box authorization timed out after {_AUTH_TIMEOUT}s. "
            "Please re-run the command to try again."
        )
    if result.get("state") != state:
        raise ValueError("OAuth state mismatch — possible CSRF. Authorization aborted.")

    res = requests.post(
        _TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": result["code"],
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        },
        timeout=15,
    )
    res.raise_for_status()
    return _store_with_expiry(res.json())


# ---------------------------------------------------------------------------
# Box API
# ---------------------------------------------------------------------------


def normalize_box_path(path: str) -> str:
    stripped = path.strip()
    if not stripped:
        raise ValueError("Box path must not be empty")

    unix_like = stripped.replace("\\", "/")

    # Convert local Box Drive paths into Box API paths.
    # Examples:
    # - /Users/me/Library/CloudStorage/Box/MyFolder/file.txt
    # - /Users/me/Library/CloudStorage/Box (Personal)/MyFolder/file.txt
    # - /Users/me/Box/MyFolder/file.txt
    local_patterns = [
        r"/(?:Library/CloudStorage/)?Box(?:\s\([^/]+\))?(/.*)?$",
        r"/(?:Library/CloudStorage/)?Box\sSync(?:\s\([^/]+\))?(/.*)?$",
    ]
    for pattern in local_patterns:
        match = re.search(pattern, unix_like)
        if match:
            suffix = match.group(1) or "/"
            return suffix if suffix.startswith("/") else f"/{suffix}"

    if stripped.startswith("/"):
        return stripped

    return f"/{stripped}"


def _box_api_request(
    method: str,
    endpoint: str,
    token: str,
    *,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
) -> requests.Response:
    res = requests.request(
        method,
        f"https://api.box.com/2.0/{endpoint}",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        json=json,
        timeout=15,
    )
    return res


def _box_error_summary(response: requests.Response) -> str:
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

    context_info = payload.get("context_info") or {}
    errors = context_info.get("errors") if isinstance(context_info, dict) else None
    if errors:
        return f"status={response.status_code}, errors={errors}"

    code = payload.get("code")
    message = payload.get("message")
    if code or message:
        return f"status={response.status_code}, code={code}, message={message}"
    return f"status={response.status_code}, body={payload}"


def _extract_box_missing_scopes(*messages: str) -> list[str]:
    found: set[str] = set()
    for message in messages:
        for scope in re.findall(r"required scope '([^']+)'", message):
            found.add(scope)
        for scope in re.findall(r"scope '([^']+)'", message):
            if "missing" in message.lower() or "required" in message.lower():
                found.add(scope)
    return sorted(found)


def _has_box_permission_error(*messages: str) -> bool:
    markers = (
        "missing_scope",
        "insufficient_scope",
        "insufficient_permissions",
        "access denied",
        "not permitted",
    )
    return any(
        any(marker in message.lower() for marker in markers) for message in messages
    )


def _list_folder_items(folder_id: str, token: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    offset = 0
    limit = 1000
    while True:
        res = _box_api_request(
            "GET",
            f"folders/{folder_id}/items",
            token,
            params={"limit": limit, "offset": offset, "fields": "id,name,type"},
        )
        res.raise_for_status()
        payload = res.json()
        items.extend(payload.get("entries", []))
        total_count = payload.get("total_count", len(items))
        offset = payload.get("offset", offset) + payload.get("limit", limit)
        if offset >= total_count:
            break
    return items


def resolve_box_folder_id(box_path: str, token: str) -> str:
    path = normalize_box_path(box_path)
    if path in {"/", ""}:
        return "0"

    segments = [segment for segment in path.strip("/").split("/") if segment]
    folder_id = "0"
    current_path = ""
    for segment in segments:
        current_path = f"{current_path}/{segment}"
        items = _list_folder_items(folder_id, token)
        match = next(
            (
                item
                for item in items
                if item.get("type") == "folder" and item.get("name") == segment
            ),
            None,
        )
        if match is None:
            raise ValueError(f"Folder not found in Box path: {current_path}")
        folder_id = str(match["id"])
    return folder_id


def get_or_create_shared_url(box_path: str, token: str) -> str:
    folder_id = resolve_box_folder_id(box_path, token)

    update_res = _box_api_request(
        "PUT",
        f"folders/{folder_id}",
        token,
        json={"shared_link": {"access": "open"}},
    )
    if update_res.ok:
        payload = update_res.json()
        shared_link = payload.get("shared_link") or {}
        url = shared_link.get("url")
        if url:
            return url

    get_res = _box_api_request(
        "GET",
        f"folders/{folder_id}",
        token,
        params={"fields": "shared_link"},
    )
    if get_res.ok:
        payload = get_res.json()
        shared_link = payload.get("shared_link") or {}
        url = shared_link.get("url")
        if url:
            return url

    update_msg = _box_error_summary(update_res)
    get_msg = _box_error_summary(get_res)
    missing_scopes = _extract_box_missing_scopes(update_msg, get_msg)
    scope_hint = ""
    if missing_scopes:
        joined = ", ".join(missing_scopes)
        scope_hint = (
            " Required Box app scopes are missing: "
            f"{joined}. Update app permissions in the Box Developer Console, "
            "then generate a new access token."
        )
    elif _has_box_permission_error(update_msg, get_msg):
        scope_hint = (
            " Box token is missing required permissions. "
            "Enable access to files/folders and shared links in the Box Developer Console, "
            "then generate a new access token."
        )
    raise ValueError(
        "Box API did not return a shared URL "
        f"(folders/{folder_id} PUT: {update_msg}; folders/{folder_id} GET: {get_msg})."
        f"{scope_hint}"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create a Box shared URL, then generate a QR code and optional Bitly URL."
        )
    )
    parser.add_argument("path", help="Box path (API path or local Box Drive path)")
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
            "Print the Bitly authorization URL and prompt for the callback URL "
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

    client_id = require_env("BOX_CLIENT_ID")
    client_secret = require_env("BOX_CLIENT_SECRET")
    if not client_id or not client_secret:
        return 1

    try:
        box_token = get_box_access_token(client_id, client_secret, args.redirect_port)
    except (TimeoutError, ValueError, requests.RequestException) as exc:
        print(f"Error: Box authentication failed: {exc}", file=sys.stderr)
        return 1

    try:
        box_path = normalize_box_path(args.path)
    except ValueError as exc:
        print(f"Error: Invalid Box path: {exc}", file=sys.stderr)
        return 1

    try:
        public_url = get_or_create_shared_url(box_path, box_token)
    except (requests.RequestException, KeyError, ValueError) as exc:
        print(f"Error: Failed to get Box shared URL: {exc}", file=sys.stderr)
        return 1

    bitly_url = None
    bitly_token = None
    if not args.no_bitly:
        try:
            bitly_token = acquire_bitly_token(args.redirect_port, args.no_browser)
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

    print(f"Box path:     {box_path}")
    print(f"Public URL:   {public_url}")
    if bitly_url:
        print(f"Bitly URL:    {bitly_url}")
    print(f"QR code:      {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
