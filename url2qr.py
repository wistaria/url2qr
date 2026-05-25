#!/usr/bin/env python3
from __future__ import annotations

if __name__ == "__main__":
    from cli_common import ensure_project_venv

    ensure_project_venv()

import argparse
import sys
import requests
import qrcode

from cli_common import optional_env, parse_args_or_show_help, select_qr_text


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

    args = parse_args_or_show_help(parser, argv)
    if args is None:
        return 2

    bitly_url = None
    token = optional_env(
        "BITLY_ACCESS_TOKEN",
        "BITLY_ACCESS_TOKEN is not set; skipping Bitly URL generation.",
    )
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
