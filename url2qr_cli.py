#!/usr/bin/env python3
from __future__ import annotations

if __name__ == "__main__":
    from cli_common import ensure_project_venv

    ensure_project_venv()

import argparse
import sys

import requests

from cli_common import (
    _DEFAULT_REDIRECT_PORT,
    acquire_bitly_token,
    make_qr,
    parse_args_or_show_help,
    select_qr_text,
    shorten_with_bitly,
)


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
