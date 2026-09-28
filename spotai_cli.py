#!/usr/bin/env python3
"""
Command-Line Interface for SpotAI-Review (Topic 4 — Group 4).
Usage:
  python3 spotai_cli.py --repo sample_repos/repo1_ecommerce_java --output-dir reports/repo1 --milestone 4
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

try:
    from spotai.pipeline import SpotAIPipeline
    from spotai.github_pr_bot import GitHubPRReviewBot
    from spotai.reporter import ReportExporter
    from spotai.repo_resolver import RepoResolver, RepoResolverError
except ImportError:
    from src.spotai.pipeline import SpotAIPipeline
    from src.spotai.github_pr_bot import GitHubPRReviewBot
    from src.spotai.reporter import ReportExporter
    from src.spotai.repo_resolver import RepoResolver, RepoResolverError


def main():
    parser = argparse.ArgumentParser(
        description="SpotAI-Review: Static Code Analysis & AI Code Review Tool (SpotBugs + AST + Clone + LLM)"
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="Path to target Java/Python repository or remote Git/GitHub URL (e.g. https://github.com/user/repo)"
    )
    parser.add_argument("--output-dir", default="reports", help="Directory to write output reports")
    parser.add_argument("--clone-threshold", type=float, default=0.80, help="Clone similarity threshold (0.0 - 1.0)")
    parser.add_argument("--min-clone-lines", type=int, default=7, help="Minimum lines for clone detection")
    parser.add_argument("--max-cc", type=int, default=10, help="Cyclomatic Complexity warning threshold")
    parser.add_argument("--milestone", type=int, choices=[1, 2, 3, 4], default=4, help="Run mode matching project milestone (1..4)")
    parser.add_argument("--fail-on-gate", action="store_true", help="Exit with non-zero code if Quality Gate fails")
    parser.add_argument(
        "--cleanup-temp",
        action="store_true",
        help="Automatically delete the temporary cloned directory after analysis completes"
    )
    args = parser.parse_args()

    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfig = getattr(stream, "reconfigure", None)
        if callable(reconfig):
            try:
                reconfig(encoding="utf-8", errors="replace")
            except Exception:
                pass

    repo_dir: str = ""
    is_temp: bool = False
    repo_name: str = ""

    # Resolve local path or remote Git URL
    resolver = RepoResolver()
    try:
        repo_dir, is_temp, repo_name = resolver.resolve(args.repo)
    except RepoResolverError as err:
        print(f"\n[REPOSITORY ERROR] {err}\n", file=sys.stderr)
        sys.exit(1)

    try:
        pipeline = SpotAIPipeline(
            clone_threshold=args.clone_threshold,
            min_clone_lines=args.min_clone_lines,
            max_cc=args.max_cc,
            milestone=args.milestone,
        )
        report = pipeline.analyze(repo_dir, repo_name=repo_name)

        os.makedirs(args.output_dir, exist_ok=True)
        ReportExporter.save_json(report, os.path.join(args.output_dir, "analysis_report.json"))
        ReportExporter.save_sarif(report, os.path.join(args.output_dir, "analysis_report.sarif"))
        ReportExporter.save_html_dashboard(report, os.path.join(args.output_dir, "dashboard.html"))

        pr_bot = GitHubPRReviewBot()
        md_summary = pr_bot.build_pr_comment_markdown(report)
        with open(os.path.join(args.output_dir, "pr_comment.md"), "w", encoding="utf-8") as f:
            f.write(md_summary)
        pr_bot.post_to_github_if_configured(report, os.path.join(args.output_dir, "github_pr_payload.json"))

        print(f"=== SpotAI-Review ({report.milestone_stage}) Summary for '{report.repository_name}' ===")
        print(f"Files Scanned : {report.files_scanned} ({report.total_loc} LOC)")
        print(f"Average CC    : {report.average_cc:.2f} | Max CC: {report.max_cc} | Avg MI: {report.average_mi:.1f}")
        print(f"Total Issues  : {len(report.issues)} -> By Engine: {report.summary_by_engine}")
        print(f"Issues by Type: {report.summary_by_type}")
        print(f"Quality Gate  : {'PASSED' if report.quality_gate_passed else 'FAILED'}")
        print(f"Reports saved : {os.path.abspath(args.output_dir)}")

        if args.fail_on_gate and not report.quality_gate_passed:
            sys.exit(2)

    finally:
        if is_temp and args.cleanup_temp and repo_dir:
            print(f"[INFO] Cleaning up temporary directory: {repo_dir}")
            resolver.cleanup(repo_dir)


if __name__ == "__main__":
    main()
