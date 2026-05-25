#!/usr/bin/env python3
from __future__ import annotations

if __name__ == "__main__":
    from cli_common import ensure_project_venv

    ensure_project_venv()

import argparse
import re
import sys

import requests

from cli_common import (
    optional_env,
    parse_args_or_show_help,
    require_env,
    select_qr_text,
)
from url2qr import make_qr, shorten_with_bitly


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
            return suffix if suffix.startswith("/") else f"/{suffix}"

    # Dropbox API paths always start with '/'.
    if stripped.startswith("/"):
        return stripped

    return f"/{stripped}"


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
            "generate a new access token."
        )
    elif _has_missing_scope_error(create_msg, list_msg):
        scope_hint = (
            " Dropbox token is missing required app scopes. "
            "Enable at least sharing.read and sharing.write in Dropbox App Console, "
            "then generate a new access token."
        )
    raise ValueError(
        "Dropbox API did not return a shared URL "
        f"(create_shared_link_with_settings: {create_msg}; "
        f"list_shared_links: {list_msg}).{scope_hint}"
    )


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

    args = parse_args_or_show_help(parser, argv)
    if args is None:
        return 2

    dropbox_token = require_env("DROPBOX_ACCESS_TOKEN")
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
    bitly_token = optional_env(
        "BITLY_ACCESS_TOKEN",
        "BITLY_ACCESS_TOKEN is not set; skipping Bitly URL generation.",
    )
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
