"""Incremental PR gate with a full-repository baseline and unchanged smell thresholds."""

import re
from collections import Counter

from .models import AnalysisReport


def _normalize_path(path):
    return path.replace("\\", "/")


def _issue_signature(issue):
    partner = re.sub(r":\d+-\d+", "", issue.get("clone_partner") or "")
    return (
        _normalize_path(issue["file_path"]),
        issue["source_engine"],
        issue["smell_or_bug_type"],
        issue["entity_name"],
        _normalize_path(partner),
    )


def _serious_issues(issues):
    return Counter(
        _issue_signature(issue)
        for issue in issues
        if issue["severity"] in ("HIGH", "CRITICAL")
    )


def _method_complexity(metrics):
    complexity = {}
    for metric in metrics:
        key = (_normalize_path(metric["file_path"]), metric["method_name"])
        complexity[key] = max(complexity.get(key, 0), metric["cyclomatic_complexity"])
    return complexity


def apply_incremental_quality_gate(report: AnalysisReport, baseline: dict, baseline_commit: str, max_cc: int):
    """Fail PRs that introduce serious findings or new/worsened excessive complexity.

    The original repository-wide gate result stays visible in pr_gate. This
    function only changes the CI outcome when an explicit baseline is supplied.
    """
    current = report.to_dict()
    new_issues = _serious_issues(current["issues"]) - _serious_issues(baseline["issues"])
    current_cc = _method_complexity(current["method_metrics"])
    baseline_cc = _method_complexity(baseline["method_metrics"])
    complexity_regressions = sum(
        complexity > max_cc and complexity > baseline_cc.get(method, 0)
        for method, complexity in current_cc.items()
    )
    invalid_current = report.files_scanned == 0 or any(
        issue.smell_or_bug_type == "ANALYSIS_ERROR" for issue in report.issues
    )
    invalid_baseline = baseline["files_scanned"] == 0 or any(
        issue["smell_or_bug_type"] == "ANALYSIS_ERROR" for issue in baseline["issues"]
    )
    total_new_high = sum(new_issues.values())
    full_repo_passed = report.quality_gate_passed
    report.quality_gate_passed = (
        not invalid_current and not invalid_baseline
        and total_new_high == 0 and complexity_regressions == 0
    )
    report.pr_gate = {
        "mode": "incremental",
        "baseline_commit": baseline_commit,
        "full_repository_quality_gate_passed": full_repo_passed,
        "new_high_or_critical": total_new_high,
        "complexity_regressions": complexity_regressions,
        "baseline_valid": not invalid_baseline,
        "current_valid": not invalid_current,
    }
