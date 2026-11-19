"""Проверить кеш релиза или установить wheel в его окончательный путь."""

import fcntl
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path


def verify_wheel(wheel: Path, expected: str) -> None:
    with wheel.open("rb") as source:
        actual = hashlib.file_digest(source, "sha256").hexdigest()
    if actual != expected:
        raise SystemExit(f"SHA256 mismatch for {wheel.name}: expected {expected}, got {actual}")


def verify_installation(venv: Path, version: str) -> None:
    result = subprocess.check_output(
        [
            venv / "bin/python",
            "-I",
            "-c",
            "from importlib.metadata import version; print(version('orders'))",
        ],
        text=True,
    )
    if result.strip() != version:
        raise SystemExit(f"Expected orders {version}, installed {result.strip()}")
    for executable in ("orders-migrate", "uvicorn"):
        if not os.access(venv / "bin" / executable, os.X_OK):
            raise SystemExit(f"Missing executable in {venv}: {executable}")


def prepare(release: Path, expected: str) -> None:
    root = release.parent.parent
    wheel = release / f"orders-{release.name}-py3-none-any.whl"
    marker = release / ".sha256"
    venv = release / "venv"
    release.mkdir(parents=True, exist_ok=True)
    with (release / ".install.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if marker.is_file():
            pinned = marker.read_text().strip()
            if expected and pinned != expected:
                raise SystemExit(f"SHA256 conflicts with verified release {release.name}")
            verify_wheel(wheel, pinned)
            verify_installation(venv, release.name)
            return

        if not expected or (root / "current").resolve() == release.resolve():
            raise SystemExit(f"Cannot rebuild {release.name} without a verified, inactive wheel")
        source = root / "artifacts" / expected / wheel.name
        verify_wheel(source, expected)
        shutil.copyfile(source, wheel)
        # Сценарии в bin/ содержат абсолютные пути. Окружение сразу строится на месте.
        subprocess.run([sys.executable, "-m", "venv", "--clear", venv], check=True)
        subprocess.run(
            [venv / "bin/python", "-m", "pip", "install", "--disable-pip-version-check", wheel],
            check=True,
        )
        verify_installation(venv, release.name)
        pending = release / ".sha256.tmp"
        pending.write_text(expected + "\n")
        pending.replace(marker)
        print("installed")


if __name__ == "__main__":
    prepare(Path(sys.argv[1]), sys.argv[2].removeprefix("sha256:") if len(sys.argv) > 2 else "")
