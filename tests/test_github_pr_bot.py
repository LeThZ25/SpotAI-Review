"""GitHub PR publishing tests that never make network requests."""

import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import spotai_cli
from spotai.github_pr_bot import GitHubPRPublishError, GitHubPRReviewBot
from spotai.models import AnalysisReport, CodeIssue

SAMPLE_REPORT_LOC = 50
SAMPLE_MAINTAINABILITY = 75.0
EXISTING_BOT_COMMENT_ID = 77


def sample_report(passed=True):
    issues = [] if passed else [
        CodeIssue(
            "AST-001", "AST-Smell", "CODE_SMELL", "Long Method", "HIGH",
            "src/example.py", 1, SAMPLE_REPORT_LOC, "example", "Method is too long",
            ai_explanation="Split the function into smaller parts.",
            ai_refactored_code="def example():\n    return 1",
            ai_limitations="Confirm behavior with tests.",
        )
    ]
    return AnalysisReport(
        repository_name="sample", milestone_stage="Milestone-4", files_scanned=1,
        total_loc=SAMPLE_REPORT_LOC, average_cc=2.0, max_cc=5,
        average_mi=SAMPLE_MAINTAINABILITY,
        quality_gate_passed=passed, issues=issues,
        summary_by_engine={"AST-Smell": len(issues)},
    )


class TestGitHubPRPublishing(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.event_path = Path(self.temp.name, "event.json")
        self.event_path.write_text(json.dumps({"pull_request": {"number": 42}}), encoding="utf-8")
        self.payload_path = str(Path(self.temp.name, "review_payload.json"))
        self.env = patch.dict(os.environ, {
            "GITHUB_TOKEN": "test-token", "GITHUB_REPOSITORY": "group/spotai",
            "GITHUB_EVENT_PATH": str(self.event_path),
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    @staticmethod
    def response(body):
        return io.BytesIO(json.dumps(body).encode("utf-8"))

    def fake_comments_api(self, requests, comments, result_id):
        def fake_open(request, timeout):
            requests.append(request)
            if request.get_method() == "GET":
                return self.response(comments)
            return self.response({"id": result_id})
        return fake_open

    def test_comment_distinguishes_gate_conditions_from_informational_metrics(self):
        comment = GitHubPRReviewBot().build_pr_comment_markdown(sample_report(False))
        self.assertIn("| **HIGH/CRITICAL Issues** | **1** | 0 required for PASS |", comment)
        self.assertIn("| **Max Method Cyclomatic Complexity** | 5 | <= 10 |", comment)
        self.assertIn("| **Average Maintainability Index (MI)** | 75.0 / 100 | Informational |", comment)
        self.assertIn("| **Average Cyclomatic Complexity (CC)** | 2.00 | Informational |", comment)

    def test_incremental_pr_comment_discloses_legacy_repository_findings(self):
        report = sample_report(False)
        report.quality_gate_passed = True
        report.pr_gate = {
            "baseline_commit": "previous-commit",
            "new_high_or_critical": 0,
            "complexity_regressions": 0,
        }
        comment = GitHubPRReviewBot().build_pr_comment_markdown(report)
        self.assertIn("**Quality Gate:** **PASSED**", comment)
        self.assertIn("**HIGH/CRITICAL Issues** | **1** | Full repository (informational)", comment)
        self.assertIn("**New HIGH/CRITICAL Issues** | **0** | 0 required for PR PASS", comment)
        self.assertIn("**New/Worsened Complexity Violations** | **0**", comment)
        self.assertIn("`previous-commit`", comment)

    def test_creates_comment_if_no_bot_summary_exists(self):
        calls = []
        others = [{"id": 1, "user": {"login": "some-developer"},
                   "body": GitHubPRReviewBot.COMMENT_MARKER}]
        fake_open = self.fake_comments_api(calls, others, result_id=123)
        with patch("urllib.request.urlopen", side_effect=fake_open):
            self.assertTrue(GitHubPRReviewBot().post_to_github_if_configured(sample_report(False), self.payload_path))

        self.assertEqual([request.get_method() for request in calls], ["GET", "POST"])
        self.assertIn("/issues/42/comments?per_page=100&page=1", calls[0].full_url)
        self.assertEqual(calls[1].full_url, "https://api.github.com/repos/group/spotai/issues/42/comments")
        posted_body = json.loads(calls[1].data.decode("utf-8"))["body"]
        self.assertIn(GitHubPRReviewBot.COMMENT_MARKER, posted_body)
        self.assertIn("FAILED (Action Required)", posted_body)
        self.assertIn("Split the function", posted_body)
        self.assertEqual(json.loads(Path(self.payload_path).read_text(encoding="utf-8"))["event"], "REQUEST_CHANGES")

    def test_updates_existing_bot_summary(self):
        calls = []
        comments = [{"id": EXISTING_BOT_COMMENT_ID,
                     "user": {"login": "github-actions[bot]"},
                     "body": GitHubPRReviewBot.COMMENT_MARKER + " older result"}]
        fake_open = self.fake_comments_api(calls, comments, EXISTING_BOT_COMMENT_ID)
        with patch("urllib.request.urlopen", side_effect=fake_open):
            self.assertTrue(GitHubPRReviewBot().post_to_github_if_configured(sample_report(), self.payload_path))

        self.assertEqual([request.get_method() for request in calls], ["GET", "PATCH"])
        self.assertEqual(calls[1].full_url, f"https://api.github.com/repos/group/spotai/issues/comments/{EXISTING_BOT_COMMENT_ID}")
        self.assertIn("PASSED", json.loads(calls[1].data.decode("utf-8"))["body"])

    def test_finds_existing_comment_on_later_page(self):
        methods = []

        def fake_open(req, timeout):
            methods.append(req.get_method())
            if req.get_method() == "PATCH":
                return self.response({"id": 88})
            if "&page=1" in req.full_url:
                return self.response([{"id": i, "user": {"login": "other"}, "body": "hello"} for i in range(100)])
            return self.response([{
                "id": 88, "user": {"login": "github-actions[bot]"},
                "body": GitHubPRReviewBot.COMMENT_MARKER,
            }])

        with patch("urllib.request.urlopen", side_effect=fake_open):
            self.assertTrue(GitHubPRReviewBot().post_to_github_if_configured(sample_report(), self.payload_path))
        self.assertEqual(methods, ["GET", "GET", "PATCH"])

    def test_reports_http_errors_and_keeps_saved_payload(self):
        for status, reason in [(401, "Unauthorized"), (403, "Forbidden")]:
            with self.subTest(status=status):
                error = urllib.error.HTTPError("https://api.github.com/", status, reason, None, None)
                with patch("urllib.request.urlopen", side_effect=error):
                    with self.assertRaisesRegex(GitHubPRPublishError, f"HTTP {status}"):
                        GitHubPRReviewBot().post_to_github_if_configured(sample_report(), self.payload_path)
                self.assertTrue(Path(self.payload_path).exists())

    def test_missing_token_does_not_contact_github(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": ""}):
            with patch("urllib.request.urlopen") as api:
                self.assertFalse(GitHubPRReviewBot().post_to_github_if_configured(sample_report(), self.payload_path))
                api.assert_not_called()
        self.assertTrue(Path(self.payload_path).exists())

    def test_missing_pr_number_does_not_contact_github(self):
        for event in ({"workflow_dispatch": {}}, {"pull_request": None}):
            with self.subTest(event=event):
                self.event_path.write_text(json.dumps(event), encoding="utf-8")
                with patch("urllib.request.urlopen") as api:
                    self.assertFalse(GitHubPRReviewBot().post_to_github_if_configured(sample_report(), self.payload_path))
                    api.assert_not_called()

    def test_cli_gate_runs_after_successful_publish(self):
        output = str(Path(self.temp.name, "cli-reports"))
        args = ["spotai_cli.py", "--repo", str(ROOT / "sample_repos" / "repo1_ecommerce_java"),
                "--output-dir", output, "--milestone", "1", "--publish-pr-comment", "--fail-on-gate"]
        with patch.object(sys, "argv", args):
            with patch.object(GitHubPRReviewBot, "post_to_github_if_configured", return_value=True) as publish:
                with self.assertRaises(SystemExit) as result:
                    spotai_cli.main()
        self.assertEqual(result.exception.code, 2)
        publish.assert_called_once()
        self.assertTrue(Path(output, "analysis_report.json").is_file())
        self.assertTrue(Path(output, "analysis_report.sarif").is_file())
        self.assertTrue(Path(output, "dashboard.html").is_file())
        self.assertTrue(Path(output, "pr_comment.md").is_file())

    def test_cli_clean_gate_passes_after_successful_publish(self):
        output = str(Path(self.temp.name, "clean-cli-reports"))
        args = ["spotai_cli.py", "--repo", str(ROOT / "sample_repos" / "repo3_clean_python"),
                "--output-dir", output, "--milestone", "1", "--publish-pr-comment", "--fail-on-gate"]
        with patch.object(sys, "argv", args):
            with patch.object(GitHubPRReviewBot, "post_to_github_if_configured", return_value=True) as publish:
                spotai_cli.main()
        publish.assert_called_once()
        self.assertTrue(Path(output, "analysis_report.json").is_file())
        self.assertTrue(Path(output, "analysis_report.sarif").is_file())
        self.assertTrue(Path(output, "dashboard.html").is_file())
        self.assertTrue(Path(output, "pr_comment.md").is_file())

    def test_cli_publish_failure_keeps_reports(self):
        output = str(Path(self.temp.name, "failed-publish"))
        args = ["spotai_cli.py", "--repo", str(ROOT / "sample_repos" / "repo3_clean_python"),
                "--output-dir", output, "--publish-pr-comment"]
        with patch.object(sys, "argv", args):
            with patch.object(GitHubPRReviewBot, "post_to_github_if_configured", side_effect=GitHubPRPublishError("HTTP 403 Forbidden")):
                with self.assertRaises(SystemExit) as result:
                    spotai_cli.main()
        self.assertEqual(result.exception.code, 1)
        self.assertTrue(Path(output, "analysis_report.json").is_file())


if __name__ == "__main__":
    unittest.main()
