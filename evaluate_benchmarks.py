#!/usr/bin/env python3
"""
Evaluates SpotAI-Review on the 3 sample repositories using observed static-analysis metrics.
Precision/recall and post-refactoring complexity need independently labeled ground truth.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from spotai.pipeline import SpotAIPipeline
from spotai.reporter import ReportExporter
from spotai.github_pr_bot import GitHubPRReviewBot


def run_evaluation():
    repos = [
        ("repo1_ecommerce_java", os.path.join(os.path.dirname(__file__), "sample_repos", "repo1_ecommerce_java")),
        ("repo2_payment_gateway", os.path.join(os.path.dirname(__file__), "sample_repos", "repo2_payment_gateway")),
        ("repo3_clean_python", os.path.join(os.path.dirname(__file__), "sample_repos", "repo3_clean_python")),
    ]
    pipeline = SpotAIPipeline(clone_threshold=0.80, min_clone_lines=7, max_cc=10, max_method_lines=35, milestone=4)
    eval_results = []

    for name, path in repos:
        started = time.perf_counter()
        report = pipeline.analyze(path, repo_name=name)
        analysis_seconds = round(time.perf_counter() - started, 4)
        out_dir = os.path.join(os.path.dirname(__file__), "reports", name)
        os.makedirs(out_dir, exist_ok=True)
        ReportExporter.save_json(report, os.path.join(out_dir, "analysis_report.json"))
        ReportExporter.save_sarif(report, os.path.join(out_dir, "analysis_report.sarif"))
        ReportExporter.save_html_dashboard(report, os.path.join(out_dir, "dashboard.html"))
        pr_bot = GitHubPRReviewBot()
        with open(os.path.join(out_dir, "pr_comment.md"), "w", encoding="utf-8") as f:
            f.write(pr_bot.build_pr_comment_markdown(report))

        total_warnings = len(report.issues)

        eval_results.append({
            "repository": name,
            "files_scanned": report.files_scanned,
            "total_loc": report.total_loc,
            "total_warnings": total_warnings,
            "analysis_seconds": analysis_seconds,
            "timing_method": "Single local wall-clock measurement using time.perf_counter; not an averaged performance claim.",
            "true_positives": None,
            "false_positives": None,
            "false_negatives": None,
            "precision": None,
            "recall": None,
            "f1_score": None,
            "accuracy_method": "Not measured: requires independently labeled findings and missed issues.",
            "avg_cc_before": round(report.average_cc, 2),
            "max_cc_before": report.max_cc,
            "avg_cc_after_ai_refactoring": None,
            "cc_after_method": "Not measured: suggested changes must be applied, parsed and re-analyzed.",
            "quality_gate_passed": report.quality_gate_passed,
            "engine_status": report.engine_status,
            "by_engine": report.summary_by_engine,
            "by_type": report.summary_by_type,
        })

    summary_path = os.path.join(os.path.dirname(__file__), "reports", "evaluation_benchmark.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(eval_results, f, indent=2)
    print(json.dumps(eval_results, indent=2))


if __name__ == "__main__":
    run_evaluation()
