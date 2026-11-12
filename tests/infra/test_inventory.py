"""Inventory must remain usable on Windows and after failed OpenTofu commands."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.write_inventory import write_inventory


class InventoryTests(unittest.TestCase):
    def test_successful_warning_does_not_replace_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "inventory.ini"
            target.write_bytes(b"previous inventory\n")
            result = subprocess.CompletedProcess(
                [], 0, stdout="Warning: No outputs found\n", stderr=""
            )
            with patch("scripts.write_inventory.subprocess.run", return_value=result):
                with self.assertRaises(ValueError):
                    write_inventory(Path(directory), target)
            self.assertEqual(target.read_bytes(), b"previous inventory\n")

    def test_writes_utf8_without_bom_even_for_non_ascii_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "пара" / "inventory.ini"
            output = "[app]\nserver-1 ansible_host=host.docker.internal ansible_port=2201\n# пара\n"
            result = subprocess.CompletedProcess([], 0, stdout=json.dumps(output), stderr="")
            with patch("scripts.write_inventory.subprocess.run", return_value=result):
                write_inventory(Path(directory), target)
            self.assertTrue(target.is_file())
            self.assertEqual(target.read_bytes(), output.encode("utf-8"))

    def test_failed_tofu_preserves_previous_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "inventory.ini"
            target.write_bytes(b"previous inventory\n")
            failure = subprocess.CalledProcessError(1, ["tofu"], stderr="Output not found")
            with patch("scripts.write_inventory.subprocess.run", side_effect=failure):
                with self.assertRaises(subprocess.CalledProcessError):
                    write_inventory(Path(directory), target)
            self.assertEqual(target.read_bytes(), b"previous inventory\n")

    def test_empty_output_does_not_replace_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "inventory.ini"
            target.write_bytes(b"previous inventory\n")
            result = subprocess.CompletedProcess([], 0, stdout=json.dumps(" \n"), stderr="")
            with patch("scripts.write_inventory.subprocess.run", return_value=result):
                with self.assertRaises(ValueError):
                    write_inventory(Path(directory), target)
            self.assertEqual(target.read_bytes(), b"previous inventory\n")


if __name__ == "__main__":
    unittest.main()
