"""
Module 5: GitHub Actions Pull Request Review Bot
Owner: Duong Quoc Toan (DTC235210055)
Formats analysis results into GitHub Pull Request Summary Markdown and inline review comments
using the GitHub REST API (or saves the PR review payload for artifact inspection in CI).
"""
import json
import os
import urllib.request
from typing import Dict, Any
from .models import AnalysisReport


class GitHubPRReviewBot:
    def __init__(self):
        self.github_token = os.environ.get("GITHUB_TOKEN", "")
        self.repo = os.environ.get("GITHUB_REPOSITORY", "")
        self.event_path = os.environ.get("GITHUB_EVENT_PATH", "")

    def build_pr_comment_markdown(self, report: AnalysisReport) -> str:
        gate_badge = "PASSED" if report.quality_gate_passed else "FAILED (Action Required)"
        lines = [
            f"## SpotAI-Review: Automated Static Analysis & AI Refactoring Report",
            f"**Repository:** `{report.repository_name}` | **Quality Gate:** **{gate_badge}**",
            "",
            "### 1. Executive Summary Metrics",
            "| Metric | Value | Threshold / Target |",
            "| :--- | :---: | :---: |",
            f"| **Files Scanned** | {report.files_scanned} | All changed & target files |",
            f"| **Total Lines of Code (LOC)** | {report.total_loc} | - |",
            f"| **Total Issues Detected** | **{len(report.issues)}** | 0 HIGH severity issues |",
            f"| **Average Cyclomatic Complexity (CC)** | {report.average_cc:.2f} | <= 10.0 |",
            f"| **Max Method Cyclomatic Complexity** | {report.max_cc} | <= 10 |",
            f"| **Average Maintainability Index (MI)** | {report.average_mi:.1f} / 100 | >= 65.0 |",
            "",
            "### 2. Issues Breakdown by Detection Engine",
            "| Engine | Count | Primary Focus |",
            "| :--- | :---: | :--- |",
        ]
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
            cc_badge = (
                f" | **CC Reduction:** `{issue.cyclomatic_complexity} -> {issue.verified_cc_after}`"
                if issue.cyclomatic_complexity and issue.verified_cc_after
                else ""
            )
            lines.extend([
                f"#### [{issue.severity}] `{issue.issue_id}` — {issue.smell_or_bug_type} (`{issue.source_engine}`)",
                f"- **Location:** `{issue.file_path}:{issue.start_line}-{issue.end_line}` in `{issue.entity_name}`{cc_badge}",
                f"- **Finding:** {issue.message}",
                f"- **AI Engineering Rationale:** {issue.ai_explanation or 'N/A'}",
                "- **AI Suggested Refactoring:**",
                "```java" if issue.file_path.endswith(".java") else "```python",
                issue.ai_refactored_code or "// No suggestion generated",
                "```",
                f"- **Stated Limitations & Edge Cases:** _{issue.ai_limitations or 'Verify with unit tests before merging.'}_",
                "",
            ])
        return "\n".join(lines)

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

    def post_to_github_if_configured(self, report: AnalysisReport, output_payload_path: str) -> bool:
        payload = self.build_pr_review_payload(report)
        os.makedirs(os.path.dirname(os.path.abspath(output_payload_path)), exist_ok=True)
        with open(output_payload_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        if not (self.github_token and self.repo and self.event_path and os.path.exists(self.event_path)):
            return False

        try:
            with open(self.event_path, "r", encoding="utf-8") as f:
                ev = json.load(f)
            pr_number = ev.get("pull_request", {}).get("number")
            if not pr_number:
                return False
            url = f"https://api.github.com/repos/{self.repo}/issues/{pr_number}/comments"
            req = urllib.request.Request(
                url,
                data=json.dumps({"body": payload["body"]}).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.github_token}",
                    "Accept": "application/vnd.github+json",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                return 200 <= resp.status < 300
        except Exception:
            return False
