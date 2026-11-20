"""Dependency-independent tests for the Web upload and path security rules."""
import importlib.util
import io
import os
import stat
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    from spotai import web_security
except ModuleNotFoundError as error:
    if error.name != "fastapi":
        raise

    class HTTPException(Exception):
        def __init__(self, status_code, detail):
            self.status_code = status_code
            self.detail = detail
            super().__init__(detail)

    fastapi_stub = types.ModuleType("fastapi")
    fastapi_stub.HTTPException = HTTPException
    fastapi_stub.UploadFile = type("UploadFile", (), {})
    spec = importlib.util.spec_from_file_location(
        "isolated_spotai_web_security", ROOT / "src" / "spotai" / "web_security.py"
    )
    with patch.dict(sys.modules, {"fastapi": fastapi_stub}):
        web_security = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(web_security)


def make_zip(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, content in entries:
            # Preserve hostile Windows separators in the ZIP entry test fixture.
            entry = zipfile.ZipInfo(filename)
            entry.filename = filename
            archive.writestr(entry, content)
    return buffer.getvalue()


class TestWebSecurity(unittest.TestCase):
    def test_allowed_repository_roots(self):
        self.assertTrue(web_security.allowed_local_repository(str(ROOT / "sample_repos")))
        with tempfile.TemporaryDirectory() as outside:
            with patch.dict(os.environ, {"SPOTAI_ALLOWED_ROOTS": ""}):
                self.assertFalse(web_security.allowed_local_repository(outside))
            with patch.dict(os.environ, {"SPOTAI_ALLOWED_ROOTS": outside}):
                self.assertTrue(web_security.allowed_local_repository(outside))

    def test_github_https_allowlist(self):
        self.assertTrue(web_security.validate_github_https("https://github.com/owner/repo.git"))
        for url in (
            "http://github.com/owner/repo", "https://github.com.evil.test/owner/repo",
            "https://github.com/owner/repo/tree/main", "https://github.com/owner/repo?x=1",
            "https://evil.test/owner/repo", "https://github.com:444/owner/repo",
            "https://github.com@evil.test/owner/repo", "https://github.com/../repo",
        ):
            with self.subTest(url=url):
                self.assertFalse(web_security.validate_github_https(url))

    def test_validate_report_id(self):
        self.assertTrue(web_security.validate_report_id("upload_123abc"))
        for name in ("../secrets", "a/b", "a\\b", "", "a" * 101):
            self.assertFalse(web_security.validate_report_id(name))

    def test_extract_zip_inside_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            archive_path = destination / "upload.zip"
            archive_path.write_bytes(make_zip([("source/a.py", "print('safe')")]))
            entries, expanded = web_security.extract_zip_safely(archive_path, destination)
            self.assertEqual(entries, 1)
            self.assertEqual(expanded, len("print('safe')"))
            self.assertEqual((destination / "source" / "a.py").read_text(), "print('safe')")

    def test_reject_zip_traversal_and_absolute_paths(self):
        for name in ("../escape.py", "/root.py", "C:/drive.py", "..\\escape.py"):
            with self.subTest(filename=name), tempfile.TemporaryDirectory() as directory:
                destination = Path(directory)
                archive_path = destination / "upload.zip"
                archive_path.write_bytes(make_zip([(name, "unsafe")]))
                with self.assertRaises(web_security.HTTPException) as raised:
                    web_security.extract_zip_safely(archive_path, destination)
                self.assertEqual(raised.exception.status_code, 400)

    def test_reject_zip_duplicate_case_insensitively(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            archive_path = destination / "upload.zip"
            archive_path.write_bytes(make_zip([("Code.py", "x"), ("code.py", "y")]))
            with self.assertRaises(web_security.HTTPException) as raised:
                web_security.extract_zip_safely(archive_path, destination)
            self.assertEqual(raised.exception.status_code, 400)

    def test_reject_zip_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            archive_path = destination / "upload.zip"
            entry = zipfile.ZipInfo("link.py")
            entry.create_system = 3
            entry.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(entry, "target.py")
            with self.assertRaises(web_security.HTTPException) as raised:
                web_security.extract_zip_safely(archive_path, destination)
            self.assertEqual(raised.exception.status_code, 400)

    def test_reject_zip_expanded_size_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            archive_path = destination / "upload.zip"
            archive_path.write_bytes(make_zip([("big.py", "0123456789")]))
            with patch.object(web_security, "MAX_EXTRACTED_BYTES", 5):
                with self.assertRaises(web_security.HTTPException) as raised:
                    web_security.extract_zip_safely(archive_path, destination)
            self.assertEqual(raised.exception.status_code, 413)

    def test_reject_zip_entry_count_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            archive_path = destination / "upload.zip"
            archive_path.write_bytes(make_zip([("first.py", "a"), ("second.py", "b")]))
            with patch.object(web_security, "MAX_ARCHIVE_ENTRIES", 1):
                with self.assertRaises(web_security.HTTPException) as raised:
                    web_security.extract_zip_safely(archive_path, destination)
            self.assertEqual(raised.exception.status_code, 413)


if __name__ == "__main__":
    unittest.main()
