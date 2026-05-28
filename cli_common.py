from __future__ import annotations

import argparse
import getpass
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


_CONFIG_DIR = Path.home() / ".config" / "url2qr"
_BITLY_CREDENTIALS_CACHE = _CONFIG_DIR / "bitly_credentials.json"
_BITLY_TOKEN_CACHE = _CONFIG_DIR / "bitly_tokens.json"
_BITLY_AUTH_URL = "https://bitly.com/oauth/authorize"
_BITLY_TOKEN_URL = "https://api-ssl.bitly.com/oauth/access_token"
_DEFAULT_REDIRECT_PORT = 8080
_AUTH_TIMEOUT = 120


def ensure_project_venv() -> None:
    """Create/use the temp virtual environment before third-party imports."""
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


def config_path(filename: str) -> Path:
    return _CONFIG_DIR / filename


def load_cached_fields(path: Path, required_fields: tuple[str, ...]) -> dict | None:
    data = _read_json_file(path)
    if not isinstance(data, dict):
        return None
    return data if all(data.get(field) for field in required_fields) else None


def save_cached_fields(path: Path, data: dict) -> None:
    _write_secure_json(path, data)


def prompt_required_text(prompt: str, *, secret: bool = False) -> str:
    while True:
        value = _prompt_text(prompt, secret=secret).strip()
        if value:
            return value
        print("Value must not be empty.", file=sys.stderr)


def prompt_optional_secret(prompt: str) -> str | None:
    value = _prompt_text(prompt, secret=True).strip()
    return value or None


def prompt_oauth_credentials(
    service: str,
    cache_path: Path,
    *,
    client_id_label: str = "Client ID",
    client_secret_label: str = "Client Secret",
) -> dict:
    cached = load_cached_fields(cache_path, ("client_id", "client_secret"))
    if cached:
        return cached

    print(f"{service} OAuth credentials are not configured.")
    print(f"They will be saved to {cache_path} with file mode 600.")
    client_id = prompt_required_text(f"{service} {client_id_label}: ")
    client_secret = prompt_required_text(
        f"{service} {client_secret_label}: ", secret=True
    )
    credentials = {"client_id": client_id, "client_secret": client_secret}
    save_cached_fields(cache_path, credentials)
    return credentials


def acquire_bitly_token(
    redirect_port: int = _DEFAULT_REDIRECT_PORT,
    no_browser: bool = False,
    configure: bool = False,
) -> str | None:
    cached = _load_bitly_tokens()
    if cached:
        return str(cached["access_token"])

    if not configure:
        return None

    token = prompt_optional_secret(
        "Bitly access token (leave empty for OAuth, type 'skip' to skip): "
    )
    if token and token.lower() == "skip":
        print(
            "Warning: Bitly not configured; skipping URL shortening.",
            file=sys.stderr,
        )
        return None

    if token:
        _save_bitly_tokens({"access_token": token, "source": "manual"})
        return token

    credentials = prompt_oauth_credentials("Bitly", _BITLY_CREDENTIALS_CACHE)
    return get_bitly_access_token(
        str(credentials["client_id"]),
        str(credentials["client_secret"]),
        redirect_port,
        no_browser,
    )


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
    data = _read_json_file(_BITLY_TOKEN_CACHE)
    return data if isinstance(data, dict) and "access_token" in data else None


def _save_bitly_tokens(tokens: dict) -> None:
    _write_secure_json(_BITLY_TOKEN_CACHE, tokens)


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
        headers={"Accept": "application/json"},
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=15,
    )
    res.raise_for_status()
    tokens = _parse_bitly_token_response(res)
    _save_bitly_tokens(tokens)
    return tokens


def _parse_bitly_token_response(response: object) -> dict:
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        tokens = payload
    else:
        body = getattr(response, "text", "")
        parsed = parse_qs(body)
        tokens = {key: values[0] for key, values in parsed.items() if values}

    if not tokens.get("access_token"):
        raise ValueError("Bitly token response did not include an access_token.")
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


def _prompt_text(prompt: str, *, secret: bool) -> str:
    if secret:
        return getpass.getpass(prompt)
    return input(prompt)


def _read_json_file(path: Path) -> object | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _write_secure_json(path: Path, data: dict) -> None:
    _ensure_config_dir()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    path.chmod(0o600)


def _ensure_config_dir() -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _CONFIG_DIR.chmod(0o700)
    except OSError:
        pass


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
