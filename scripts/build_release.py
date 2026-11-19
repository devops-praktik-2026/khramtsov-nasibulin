"""Собрать wheel orders и записать контрольную сумму для установки Ansible."""

import argparse
import hashlib
import subprocess
import sys
import tomllib
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("services/orders"))
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--tag", help="Метка выпуска, например v0.1.0")
    args = parser.parse_args()

    with (args.source / "pyproject.toml").open("rb") as config:
        version = tomllib.load(config)["project"]["version"]
    if args.tag is not None and args.tag != f"v{version}":
        parser.exit(1, f"Метка {args.tag} не совпадает с версией пакета {version}\n")

    outdir = args.outdir.resolve()
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(outdir), str(args.source)],
        check=True,
    )
    wheel = outdir / f"orders-{version}-py3-none-any.whl"
    with wheel.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    (outdir / "SHA256SUMS").write_bytes(f"{digest}  {wheel.name}\n".encode("ascii"))


if __name__ == "__main__":
    main()
