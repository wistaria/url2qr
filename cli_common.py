from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
import venv
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse


BOOTSTRAP_SKIP_ENV = "URL2QR_NO_AUTO_VENV"
_BITLY_TOKEN_CACHE = Path.home() / ".config" / "url2qr" / "bitly_tokens.json"
_BITLY_AUTH_URL = "https://bitly.com/oauth/authorize"
_BITLY_TOKEN_URL = "https://api-ssl.bitly.com/oauth/access_token"
_DEFAULT_REDIRECT_PORT = 8080
_AUTH_TIMEOUT = 120


def ensure_project_venv() -> None:
    """Create/use the temp virtual environment before third-party imports."""
    if os.getenv(BOOTSTRAP_SKIP_ENV):
        return

    project_root = Path(__file__).resolve().parent
    venv_dir = _default_venv_dir()
    venv_python = _venv_python(venv_dir)
    requirements = project_root / "requirements.txt"

    if not venv_python.exists():
        print(f"Creating virtual environment: {venv_dir}", file=sys.stderr)
        try:
            venv.EnvBuilder(with_pip=True).create(venv_dir)
        except OSError as exc:
            print(
                f"Error: Failed to create virtual environment: {exc}", file=sys.stderr
            )
            raise SystemExit(1) from exc

    if requirements.exists() and _requirements_changed(requirements, venv_dir):
        print("Installing dependencies from requirements.txt...", file=sys.stderr)
        try:
            subprocess.check_call(
                [str(venv_python), "-m", "pip", "install", "-r", str(requirements)]
            )
        except subprocess.CalledProcessError as exc:
            print(f"Error: Failed to install dependencies: {exc}", file=sys.stderr)
            raise SystemExit(exc.returncode) from exc
        _write_requirements_marker(requirements, venv_dir)

    if _running_in_venv(venv_dir):
        return

    print("Restarting inside virtual environment...", file=sys.stderr)
    os.execv(str(venv_python), [str(venv_python), *sys.argv])


def require_env(name: str) -> str | None:
    value = os.getenv(name)
    if not value:
        print(f"Error: {name} is not set", file=sys.stderr)
        return None
    return value


def optional_env(name: str, missing_warning: str) -> str | None:
    value = os.getenv(name)
    if not value:
        print(f"Warning: {missing_warning}", file=sys.stderr)
        return None
    return value


def parse_args_or_show_help(
    parser: argparse.ArgumentParser, argv: list[str] | None
) -> argparse.Namespace | None:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        parser.print_help(sys.stderr)
        return None
    return parser.parse_args(args)


def select_qr_text(qr_target: str, bitly_url: str | None, public_url: str) -> str:
    return bitly_url if qr_target == "short" and bitly_url else public_url


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


def shorten_with_bitly(url: str, token: str) -> str:
    import requests

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
    import qrcode

    img = qrcode.make(text)
    img.save(output)


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
    import requests

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
        raise ValueError("OAuth state mismatch - possible CSRF. Authorization aborted.")
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
        raise ValueError("OAuth state mismatch - possible CSRF. Authorization aborted.")
    return result["code"]


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _default_venv_dir() -> Path:
    if hasattr(os, "getuid"):
        return _temp_root() / str(os.getuid()) / "url2qr"
    return _temp_root() / "url2qr"


def _temp_root() -> Path:
    if sys.platform == "darwin" and Path("/private/tmp").is_dir():
        return Path("/private/tmp")
    return Path(tempfile.gettempdir()).resolve()


def _running_in_venv(venv_dir: Path) -> bool:
    return Path(sys.prefix).resolve() == venv_dir.resolve()


def _requirements_changed(requirements: Path, venv_dir: Path) -> bool:
    marker = _requirements_marker(venv_dir)
    try:
        return marker.read_text(encoding="utf-8").strip() != _file_sha256(requirements)
    except OSError:
        return True


def _write_requirements_marker(requirements: Path, venv_dir: Path) -> None:
    _requirements_marker(venv_dir).write_text(
        _file_sha256(requirements), encoding="utf-8"
    )


def _requirements_marker(venv_dir: Path) -> Path:
    return venv_dir / ".requirements.sha256"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
