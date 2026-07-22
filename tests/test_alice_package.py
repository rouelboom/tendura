from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]


class AlicePackageTest(unittest.TestCase):
    def test_build_contains_only_runtime_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            archive = Path(temporary_directory) / "alice.zip"
            subprocess.run(
                ["bash", str(ROOT / "deploy/alice/build.sh"), str(archive)],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            with ZipFile(archive) as package:
                names = set(package.namelist())

        self.assertIn("alice_function.py", names)
        self.assertIn("requirements.txt", names)
        self.assertIn("tendura/alice/handler.py", names)
        self.assertIn("tendura/application/workouts.py", names)
        self.assertIn("tendura/training_endurance/client.py", names)
        self.assertFalse(
            any(
                name.startswith(("data/", "tendura/coros/", "tendura/telegram/"))
                or name.endswith((".env", ".pyc"))
                or "__pycache__" in name
                for name in names
            )
        )


if __name__ == "__main__":
    unittest.main()
