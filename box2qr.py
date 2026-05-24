#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Any

import requests

from url2qr import make_qr, shorten_with_bitly


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
    return any(any(marker in message.lower() for marker in markers) for message in messages)


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a Box shared URL, then generate Bitly short URL and QR code."
    )
    parser.add_argument("path", help="Box path (API path or local Box Drive path)")
    parser.add_argument("-o", "--output", default="qrcode.png", help="QR code output file")
    parser.add_argument(
        "--qr-target",
        choices=["short", "public"],
        default="public",
        help="Which URL to encode in the QR code",
    )

    args = parser.parse_args(argv)

    bitly_token = os.getenv("BITLY_ACCESS_TOKEN")
    if not bitly_token:
        print("Error: BITLY_ACCESS_TOKEN is not set", file=sys.stderr)
        return 1

    box_token = os.getenv("BOX_ACCESS_TOKEN")
    if not box_token:
        print("Error: BOX_ACCESS_TOKEN is not set", file=sys.stderr)
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

    try:
        short_url = shorten_with_bitly(public_url, bitly_token)
    except (requests.RequestException, KeyError, ValueError) as exc:
        print(f"Error: Failed to shorten URL with Bitly: {exc}", file=sys.stderr)
        return 1

    qr_text = short_url if args.qr_target == "short" else public_url
    try:
        make_qr(qr_text, args.output)
    except OSError as exc:
        print(f"Error: Failed to save QR code image: {exc}", file=sys.stderr)
        return 1

    print(f"Box path:     {box_path}")
    print(f"Public URL:   {public_url}")
    print(f"Short URL:    {short_url}")
    print(f"QR code:      {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
