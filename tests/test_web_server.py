import os
import sys
import io
import zipfile
import unittest
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from spotai.snippet_analyzer import SnippetAnalyzer
try:
    from fastapi.testclient import TestClient
    from spotai.web_server import app
    from spotai.web_security import MAX_EXTRACTED_BYTES, MAX_UPLOAD_BYTES, validate_github_https
    WEB_TEST_MISSING_DEPENDENCY = None
except ModuleNotFoundError as error:
    if error.name not in {"fastapi", "httpx", "multipart", "python_multipart"}:
        raise
    WEB_TEST_MISSING_DEPENDENCY = str(error)
    TestClient = None
    app = None


class TestSnippetAnalyzer(unittest.TestCase):
    def setUp(self):
        self.analyzer = SnippetAnalyzer()

    def test_snippet_empty_code(self):
        res = self.analyzer.analyze_snippet("", "python")
        self.assertEqual(res["status"], "error")
        self.assertIn("empty", res["message"].lower())

    def test_snippet_unsupported_language(self):
        res = self.analyzer.analyze_snippet("console.log('hi')", "javascript")
        self.assertEqual(res["status"], "unsupported_language")
        self.assertIn("not supported", res["message"].lower())

    def test_snippet_python_syntax_error(self):
        res = self.analyzer.analyze_snippet("def broken(:", "python")
        self.assertEqual(res["status"], "syntax_error")
        self.assertIn("SyntaxError", res["message"])

    def test_snippet_python_clean_code(self):
        code = "def add(x: int, y: int) -> int:\n    return x + y"
        res = self.analyzer.analyze_snippet(code, "python")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["language"], "python")
        self.assertEqual(res["summary"]["issues_count"], 0)
        self.assertTrue(res["summary"]["quality_gate_passed"])

    def test_snippet_python_smell_detection(self):
        # Long parameter list: 6 parameters (> threshold 4)
        code = "def process(a, b, c, d, e, f):\n    return a + b"
        res = self.analyzer.analyze_snippet(code, "python")
        self.assertEqual(res["status"], "success")
        self.assertGreaterEqual(res["summary"]["issues_count"], 1)
        smell_types = [i["type"] for i in res["issues"]]
        self.assertIn("Long Parameter List", smell_types)

    def test_snippet_java_smell_detection_and_wrap(self):
        # Raw Java method without class wrapper
        code = "public int process(int a, int b, int c, int d, int e) {\n    return a + b;\n}"
        res = self.analyzer.analyze_snippet(code, "java")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["language"], "java")
        self.assertGreaterEqual(res["summary"]["issues_count"], 1)
        smell_types = [i["type"] for i in res["issues"]]
        self.assertIn("Long Parameter List", smell_types)

@unittest.skipIf(TestClient is None, "Web/API dependency unavailable: " + str(WEB_TEST_MISSING_DEPENDENCY))
class TestWebServerAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_api_health(self):
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "healthy")
        self.assertIn("engines", data)

    def test_api_analyze_snippet_endpoint(self):
        res = self.client.post("/api/analyze-snippet", json={
            "code": "def multiply(a, b):\n    return a * b",
            "language": "python"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["summary"]["issues_count"], 0)

    def test_api_analyze_repo_local_valid(self):
        res = self.client.post("/api/analyze-repo", json={
            "repo": "sample_repos/repo1_ecommerce_java",
            "milestone": 1
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertGreaterEqual(data["detected_files"]["java"], 1)

    def test_api_analyze_repo_unsupported_language_alert(self):
        # .github directory contains only yml, no java or python
        res = self.client.post("/api/analyze-repo", json={
            "repo": ".github",
            "milestone": 1
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "no_supported_files")
        self.assertIn("No Java", data["message"])

    def test_api_index_html(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("SpotAI-Review", res.text)
        self.assertIn("Live Code Playground", res.text)
        self.assertIn("drop-zone", res.text)

    def test_api_upload_and_analyze_py_file(self):
        py_code = b"def calculate(x: int) -> int:\n    return x * 2\n"
        files = [("files", ("test_calc.py", py_code, "text/x-python"))]
        res = self.client.post("/api/upload-and-analyze", files=files, data={"milestone": "1"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["detected_files"]["python"], 1)

    def test_api_upload_and_analyze_unsupported_file(self):
        txt_content = b"This is just a readme file without code."
        files = [("files", ("readme.txt", txt_content, "text/plain"))]
        res = self.client.post("/api/upload-and-analyze", files=files, data={"milestone": "1"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "no_supported_files")
        self.assertIn("No Java", data["message"])

    def test_api_upload_and_analyze_zip_archive(self):
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            zf.writestr("Main.java", "public class Main { public static void main(String[] args) {} }")
        zip_buffer.seek(0)
        files = [("files", ("project.zip", zip_buffer.getvalue(), "application/zip"))]
        res = self.client.post("/api/upload-and-analyze", files=files, data={"milestone": "1"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["detected_files"]["java"], 1)

    def test_github_url_restrictions(self):
        self.assertTrue(validate_github_https("https://github.com/owner/repo.git"))
        for value in ("http://github.com/owner/repo", "https://evil.test/owner/repo",
                      "https://github.com/owner/repo?x=1", "https://github.com:broken/owner/repo",
                      "https://github.com/owner/repo/tree/main"):
            self.assertFalse(validate_github_https(value), value)

    def test_reject_outside_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            res = self.client.post("/api/analyze-repo", json={"repo": directory})
            self.assertEqual(res.status_code, 403)

    def test_reject_invalid_github_url(self):
        res = self.client.post("/api/analyze-repo", json={"repo": "https://evil.test/owner/repo"})
        self.assertEqual(res.status_code, 400)

    def test_dashboard_path_traversal(self):
        res = self.client.get("/dashboard/%2e%2e")
        self.assertIn(res.status_code, (404, 422))

    def test_reject_zip_traversal(self):
        content = io.BytesIO()
        with zipfile.ZipFile(content, "w") as archive:
            archive.writestr("../escape.py", "print('unsafe')")
        res = self.client.post("/api/upload-and-analyze",
                               files=[("files", ("bad.zip", content.getvalue(), "application/zip"))])
        self.assertEqual(res.status_code, 400)

    def test_reject_zip_bomb_metadata(self):
        content = io.BytesIO()
        with zipfile.ZipFile(content, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("huge.py", b"x" * (MAX_EXTRACTED_BYTES + 1))
        res = self.client.post("/api/upload-and-analyze",
                               files=[("files", ("large.zip", content.getvalue(), "application/zip"))])
        self.assertEqual(res.status_code, 413)

    def test_reject_oversized_upload(self):
        res = self.client.post("/api/upload-and-analyze",
                               files=[("files", ("oversize.py", b"x" * (MAX_UPLOAD_BYTES + 1), "text/plain"))])
        self.assertEqual(res.status_code, 413)

    def test_repository_dashboard_contains_escaped_code(self):
        with tempfile.TemporaryDirectory(dir=os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))) as directory:
            Path(directory, "unsafe.py").write_text(
                "def test():\n    value = '<img src=x onerror=alert(1)>'\n    return value\n",
                encoding="utf-8",
            )
            res = self.client.post("/api/analyze-repo", json={"repo": directory, "milestone": 1})
            self.assertEqual(res.status_code, 200)
            if res.json()["report"]["issues"]:
                dashboard = self.client.get(res.json()["dashboard_url"])
                self.assertEqual(dashboard.status_code, 200)
                self.assertNotIn("<img src=x onerror=alert(1)>", dashboard.text)


if __name__ == "__main__":
    unittest.main()
