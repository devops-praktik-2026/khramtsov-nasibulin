"""Save the applied OpenTofu inventory as UTF-8, including on Windows."""

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write_inventory(tofu_dir: Path, target: Path) -> None:
    result = subprocess.run(
        ["tofu", f"-chdir={tofu_dir.resolve()}", "output", "-json", "ansible_inventory"],
        check=True,
        capture_output=True,
        encoding="utf-8",
    )
    inventory = json.loads(result.stdout)
    if not isinstance(inventory, str) or not inventory.strip():
        raise ValueError("OpenTofu returned no inventory string; run tofu apply first")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(inventory, encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tofu-dir", type=Path, default=ROOT / "infra/terraform")
    parser.add_argument("--output", type=Path, default=ROOT / "infra/ansible/inventory.ini")
    args = parser.parse_args()
    try:
        write_inventory(args.tofu_dir, args.output)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        # Do not print captured OpenTofu output: backend errors can contain credentials.
        parser.exit(1, f"Inventory was not updated ({type(error).__name__}). Check tofu output.\n")
    print(f"Inventory saved: {args.output}")


if __name__ == "__main__":
    main()
