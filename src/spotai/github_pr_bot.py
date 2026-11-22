"""
Module 5: GitHub Actions Pull Request Review Bot
Owner: Duong Quoc Toan (DTC235210055)
Formats analysis results into a GitHub Pull Request summary and review payload.
Publishes or updates one GitHub Actions bot comment when PR context is available.
"""
import json
import os
import re
from http import HTTPStatus
import urllib.error
import urllib.request
from typing import Dict, Any
from .models import AnalysisReport


class GitHubPRPublishError(RuntimeError):
    """An attempted GitHub PR comment publication failed."""


class GitHubPRReviewBot:
    COMMENT_MARKER = "<!-- spotai-review:automated-pr-summary -->"
    BOT_LOGIN = "github-actions[bot]"
    API_VERSION = "2022-11-28"
    REQUEST_TIMEOUT_SECONDS = 20
    FINDING_TEXT_LIMIT = 800
    SUGGESTION_CODE_LIMIT = 1200
    LIMITATIONS_TEXT_LIMIT = 450

    def __init__(self):
        self.github_token = os.environ.get("GITHUB_TOKEN", "")
        self.repo = os.environ.get("GITHUB_REPOSITORY", "")
        self.event_path = os.environ.get("GITHUB_EVENT_PATH", "")

    def build_pr_comment_markdown(self, report: AnalysisReport) -> str:
        gate_badge = "PASSED" if report.quality_gate_passed else "FAILED (Action Required)"
        lines = [
            self.COMMENT_MARKER,
            f"## SpotAI-Review: Automated Static Analysis & AI Refactoring Report",
            f"**Repository:** `{report.repository_name}` | **Quality Gate:** **{gate_badge}**",
            "",
        ]
        lines.extend(self._summary_metrics(report))
        lines.extend([
            "",
            "### 2. Issues Breakdown by Detection Engine",
            "| Engine | Count | Primary Focus |",
            "| :--- | :---: | :--- |",
        ])
        for eng, cnt in sorted(report.summary_by_engine.items()):
            desc = (
                "Bytecode bugs, Null-pointer paths, SQLi, resource leaks"
                if eng == "SpotBugs"
                else (
                    "Type-1/2/3 token & AST duplicate code blocks"
                    if eng == "Clone-Detector"
                    else "8 structural code smells & McCabe/Cognitive complexity"
                )
            )
            lines.append(f"| **{eng}** | {cnt} | {desc} |")

        lines.extend(["", "### 3. Top Actionable Findings & AI Refactoring Suggestions"])
        for issue in report.issues[:8]:
            lines.extend(self._issue_markdown_lines(issue))
        return "\n".join(lines)

    @staticmethod
    def _summary_metrics(report):
        high_or_critical = sum(issue.severity in ("HIGH", "CRITICAL") for issue in report.issues)
        pr_gate = report.pr_gate
        high_target = "0 required for PASS" if pr_gate is None else "Full repository (informational)"
        cc_target = "<= 10" if pr_gate is None else "PR regressions checked against baseline"
        lines = [
            "### 1. Executive Summary Metrics",
            "| Metric | Value | Threshold / Target |",
            "| :--- | :---: | :---: |",
            f"| **Files Scanned** | {report.files_scanned} | Checked-out repository |",
            f"| **Total Lines of Code (LOC)** | {report.total_loc} | - |",
            f"| **Total Issues Detected** | **{len(report.issues)}** | Informational |",
            f"| **HIGH/CRITICAL Issues** | **{high_or_critical}** | {high_target} |",
            f"| **Average Cyclomatic Complexity (CC)** | {report.average_cc:.2f} | Informational |",
            f"| **Max Method Cyclomatic Complexity** | {report.max_cc} | {cc_target} |",
            f"| **Average Maintainability Index (MI)** | {report.average_mi:.1f} / 100 | Informational |",
        ]
        if pr_gate is not None:
            lines.extend([
                f"| **New HIGH/CRITICAL Issues** | **{pr_gate['new_high_or_critical']}** | 0 required for PR PASS |",
                f"| **New/Worsened Complexity Violations** | **{pr_gate['complexity_regressions']}** | 0 required for PR PASS |",
                "",
                f"**PR gate baseline:** `{pr_gate['baseline_commit']}`. "
                "Existing repository findings are included for visibility. "
                "The PR gate fails on newly introduced HIGH/CRITICAL findings, "
                "new or worsened method complexity above the configured threshold, or invalid analysis.",
            ])
        return lines

    @classmethod
    def _issue_markdown_lines(cls, issue):
        cc_badge = (
            f" | **CC Reduction:** `{issue.cyclomatic_complexity} -> {issue.verified_cc_after}`"
            if issue.cyclomatic_complexity and issue.verified_cc_after else ""
        )
        return [
            f"#### [{issue.severity}] `{issue.issue_id}` — {issue.smell_or_bug_type} (`{issue.source_engine}`)",
            f"- **Location:** `{issue.file_path}:{issue.start_line}-{issue.end_line}` in `{issue.entity_name}`{cc_badge}",
            f"- **Finding:** {issue.message[:cls.FINDING_TEXT_LIMIT]}",
            f"- **AI Engineering Rationale:** {(issue.ai_explanation or 'N/A')[:cls.FINDING_TEXT_LIMIT]}",
            "- **AI Suggested Refactoring:**",
            "```java" if issue.file_path.endswith(".java") else "```python",
            (issue.ai_refactored_code or "// No suggestion generated")[:cls.SUGGESTION_CODE_LIMIT],
            "```",
            "- **Stated Limitations & Edge Cases:** "
            f"_{(issue.ai_limitations or 'Verify with unit tests before merging.')[:cls.LIMITATIONS_TEXT_LIMIT]}_",
            "",
        ]

    def build_pr_review_payload(self, report: AnalysisReport) -> Dict[str, Any]:
        comments = []
        for issue in report.issues:
            body = (
                f"**[{issue.severity}] {issue.smell_or_bug_type}** (`{issue.source_engine}` - `{issue.issue_id}`)\n\n"
                f"{issue.message}\n\n"
                f"**Why Refactor:** {issue.ai_explanation}\n\n"
                f"**Suggested Refactoring:**\n```suggestion\n{issue.ai_refactored_code}\n```\n\n"
                f"**Limitations:** _{issue.ai_limitations}_"
            )
            comments.append({
                "path": issue.file_path,
                "line": issue.end_line,
                "side": "RIGHT",
                "body": body,
            })

        return {
            "body": self.build_pr_comment_markdown(report),
            "event": "COMMENT" if report.quality_gate_passed else "REQUEST_CHANGES",
            "comments": comments[:20],
        }

    def _request_json(self, url: str, method: str = "GET", payload: Dict[str, Any] | None = None) -> Any:
        headers = {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": self.API_VERSION,
        }
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.REQUEST_TIMEOUT_SECONDS) as resp:
                content = resp.read()
                return json.loads(content) if content else {}
        except urllib.error.HTTPError as err:
            hint = {
                HTTPStatus.UNAUTHORIZED: "Check the GITHUB_TOKEN used by the workflow.",
                HTTPStatus.FORBIDDEN: "Check pull-requests: write permission. Forked PR tokens are usually read-only.",
            }.get(err.code, "")
            raise GitHubPRPublishError(
                f"GitHub API {method} failed with HTTP {err.code} ({err.reason}). {hint}".strip()
            ) from err
        except urllib.error.URLError as err:
            raise GitHubPRPublishError(f"GitHub API connection failed: {err.reason}") from err
        except (json.JSONDecodeError, UnicodeDecodeError) as err:
            raise GitHubPRPublishError("GitHub API returned an invalid JSON response") from err
        except OSError as err:
            raise GitHubPRPublishError(f"GitHub API request failed: {err}") from err

    def post_to_github_if_configured(self, report: AnalysisReport, output_payload_path: str) -> bool:
        """Save the review payload and upsert the bot's PR summary, if configured."""
        payload = self.build_pr_review_payload(report)
        os.makedirs(os.path.dirname(os.path.abspath(output_payload_path)), exist_ok=True)
        with open(output_payload_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        if not (self.github_token and self.repo and self.event_path and os.path.exists(self.event_path)):
            return False

        pr_number = self._get_pull_request_number()
        if not (isinstance(pr_number, int) and pr_number > 0):
            return False
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", self.repo):
            raise GitHubPRPublishError("Invalid GITHUB_REPOSITORY value")

        comments_url = f"https://api.github.com/repos/{self.repo}/issues/{pr_number}/comments"
        existing_id = self._find_existing_summary(comments_url)
        if existing_id is None:
            self._request_json(comments_url, "POST", {"body": payload["body"]})
        else:
            update_url = f"https://api.github.com/repos/{self.repo}/issues/comments/{existing_id}"
            self._request_json(update_url, "PATCH", {"body": payload["body"]})
        return True

    def _get_pull_request_number(self):
        try:
            with open(self.event_path, "r", encoding="utf-8") as f:
                event = json.load(f)
            pr_data = event.get("pull_request")
            return pr_data.get("number") if isinstance(pr_data, dict) else None
        except (OSError, ValueError, TypeError) as err:
            raise GitHubPRPublishError(f"Unable to read GitHub PR event: {err}") from err

    def _find_existing_summary(self, comments_url: str):
        page = 1
        existing_id = None
        while True:
            comments = self._request_json(f"{comments_url}?per_page=100&page={page}")
            if not isinstance(comments, list):
                raise GitHubPRPublishError("GitHub API returned an invalid comment list")
            for comment in comments:
                if (comment.get("user", {}).get("login") == self.BOT_LOGIN
                        and self.COMMENT_MARKER in comment.get("body", "")):
                    existing_id = comment["id"]
            if len(comments) < 100:
                break
            page += 1
        return existing_id
