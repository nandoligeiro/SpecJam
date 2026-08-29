import tempfile
import unittest
import zipfile
from pathlib import Path

from specjam.archive import UnsafeArchiveError, extract_archive, validate_archive


class ArchiveTests(unittest.TestCase):
    def test_safe_archive_extracts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "safe.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("specjam/__main__.py", "raise SystemExit\n")
            destination = root / "out"
            extract_archive(archive, destination)
            self.assertTrue((destination / "specjam/__main__.py").exists())

    def test_parent_traversal_is_rejected_before_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "unsafe.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("../escape.txt", "do not write")
            with self.assertRaises(UnsafeArchiveError):
                validate_archive(archive)
            with self.assertRaises(UnsafeArchiveError):
                extract_archive(archive, root / "out")
            self.assertFalse((root / "escape.txt").exists())


if __name__ == "__main__":
    unittest.main()

