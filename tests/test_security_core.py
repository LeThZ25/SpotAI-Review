import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from spotai.pipeline import SpotAIPipeline
from spotai.snippet_analyzer import SnippetAnalyzer
from spotai.reporter import ReportExporter
from spotai.models import AnalysisReport, CodeIssue
from spotai.spotbugs_adapter import SpotBugsAdapter


class TestCoreSafety(unittest.TestCase):
    def test_python_consistent_between_repository_and_snippet(self):
        code = "def check(a, b, c, d, e):\n    if a > 0:\n        return a\n    return b\n"
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            Path(directory, "check.py").write_text(code, encoding="utf-8")
            report = SpotAIPipeline(milestone=1).analyze(directory)
            snippet = SnippetAnalyzer().analyze_snippet(code, "python")
        self.assertEqual(snippet["status"], "success")
        repository_issues = {(issue.smell_or_bug_type, issue.severity) for issue in report.issues}
        snippet_issues = {(issue["type"], issue["severity"]) for issue in snippet["issues"]}
        self.assertEqual(repository_issues, snippet_issues)
        self.assertEqual(report.max_cc, snippet["summary"]["max_cc"])
        self.assertEqual(report.quality_gate_passed, snippet["summary"]["quality_gate_passed"])

    def test_java_consistent_between_repository_and_snippet(self):
        code = ("class Demo {\n"
                "    int check(int a, int b, int c, int d, int e) {\n"
                "        if (a > 0) { return a; }\n"
                "        return b;\n"
                "    }\n"
                "}\n")
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            Path(directory, "Demo.java").write_text(code, encoding="utf-8")
            report = SpotAIPipeline(milestone=1).analyze(directory)
            snippet = SnippetAnalyzer().analyze_snippet(code, "java")
        self.assertEqual(snippet["status"], "success")
        repository_issues = {(issue.smell_or_bug_type, issue.severity) for issue in report.issues}
        snippet_issues = {(issue["type"], issue["severity"]) for issue in snippet["issues"]}
        self.assertEqual(repository_issues, snippet_issues)
        self.assertEqual(report.max_cc, snippet["summary"]["max_cc"])

    def test_empty_repository_fails_gate(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            report = SpotAIPipeline(milestone=1).analyze(directory)
            self.assertEqual(report.files_scanned, 0)
            self.assertFalse(report.quality_gate_passed)

    def test_syntax_error_fails_gate_with_line(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            Path(directory, "broken.py").write_text("def x(:\n pass\n", encoding="utf-8")
            report = SpotAIPipeline(milestone=1).analyze(directory)
            self.assertFalse(report.quality_gate_passed)
            issue = next(issue for issue in report.issues if issue.smell_or_bug_type == "ANALYSIS_ERROR")
            self.assertEqual(issue.start_line, 1)
            self.assertEqual(issue.severity, "HIGH")

    def test_clean_python_passes_gate(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            Path(directory, "clean.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
            report = SpotAIPipeline(milestone=1).analyze(directory)
            self.assertEqual(report.files_scanned, 1)
            self.assertTrue(report.quality_gate_passed)

    def test_submittable_clean_sample_passes_default_gate(self):
        repository = ROOT / "sample_repos" / "repo3_clean_python"
        report = SpotAIPipeline().analyze(str(repository))
        self.assertEqual(report.files_scanned, 1)
        self.assertTrue(report.quality_gate_passed)

    def test_spotbugs_xml_path_outside_repo_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            outside = Path(ROOT, "README.md")
            adapter = SpotBugsAdapter(directory, spotbugs_xml_path=str(outside))
            # Source reports cannot reference XML outside their own repository.
            issues = adapter.run_or_load()
            self.assertEqual(adapter.status, "error")
            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0].smell_or_bug_type, "ANALYSIS_ERROR")

    def test_html_escapes_untrusted_issue_fields(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            issue = CodeIssue("test", "AST-Smell", "TEST", "<svg/onload=alert(1)>",
                              "LOW", "a.py", 1, 1, "x", "<script>alert(1)</script>")
            report = AnalysisReport("test", "Milestone-1", 1, 1, 1.0, 1, 95.0, True, issues=[issue])
            dest = Path(directory, "report.html")
            ReportExporter.save_html_dashboard(report, str(dest))
            html = dest.read_text(encoding="utf-8")
            self.assertNotIn("<script>alert(1)</script>", html)
            self.assertNotIn("<svg/onload=alert(1)>", html)
            self.assertIn("&lt;script&gt;", html)

    def test_critical_issue_is_error_in_sarif_and_red_in_dashboard(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            issue = CodeIssue("critical", "AST-Smell", "SECURITY", "Critical Finding",
                              "CRITICAL", "unsafe.py", 1, 1, "unsafe", "Unsafe operation")
            report = AnalysisReport("sample", "Milestone-4", 1, 1, 1.0, 1, 95.0, False,
                                    issues=[issue])
            sarif_path = Path(directory, "analysis_report.sarif")
            html_path = Path(directory, "dashboard.html")
            ReportExporter.save_sarif(report, str(sarif_path))
            ReportExporter.save_html_dashboard(report, str(html_path))
            data = json.loads(sarif_path.read_text(encoding="utf-8"))
            self.assertEqual(data["runs"][0]["results"][0]["level"], "error")
            self.assertIn('style="background:#dc2626">CRITICAL', html_path.read_text(encoding="utf-8"))

    def test_cli_invalid_arguments_exit_two(self):
        command = [sys.executable, str(ROOT / "spotai_cli.py"), "--clone-threshold", "2",
                   "--repo", str(ROOT / "sample_repos" / "repo1_ecommerce_java")]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)

    def test_cli_gate_exit_and_reports(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            command = [sys.executable, str(ROOT / "spotai_cli.py"), "--repo",
                       str(ROOT / "sample_repos" / "repo1_ecommerce_java"), "--milestone", "1",
                       "--output-dir", directory, "--fail-on-gate"]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertFalse(json.loads(Path(directory, "analysis_report.json").read_text(encoding="utf-8"))["quality_gate_passed"])
            sarif = json.loads(Path(directory, "analysis_report.sarif").read_text(encoding="utf-8"))
            self.assertEqual(sarif["version"], "2.1.0")
            self.assertGreater(len(sarif["runs"][0]["results"]), 0)
            self.assertIn("<html", Path(directory, "dashboard.html").read_text(encoding="utf-8"))

    def test_cli_clean_sample_passes_gate_with_zero_exit(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            command = [sys.executable, str(ROOT / "spotai_cli.py"), "--repo",
                       str(ROOT / "sample_repos" / "repo3_clean_python"), "--output-dir",
                       directory, "--fail-on-gate"]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(Path(directory, "analysis_report.json").read_text(encoding="utf-8"))
            self.assertTrue(report["quality_gate_passed"])
            self.assertEqual(len(report["issues"]), 0)


if __name__ == "__main__":
    unittest.main()
