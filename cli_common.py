from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import venv


BOOTSTRAP_SKIP_ENV = "URL2QR_NO_AUTO_VENV"


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
