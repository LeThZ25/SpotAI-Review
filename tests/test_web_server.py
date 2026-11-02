import os
import sys
import io
import zipfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from spotai.snippet_analyzer import SnippetAnalyzer
from spotai.web_server import app
from fastapi.testclient import TestClient


class TestWebServerAndSnippetAnalyzer(unittest.TestCase):
    def setUp(self):
        self.analyzer = SnippetAnalyzer()
        self.client = TestClient(app)

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


if __name__ == "__main__":
    unittest.main()
