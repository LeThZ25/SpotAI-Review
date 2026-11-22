#!/usr/bin/env python3
"""
Command-Line Interface for SpotAI-Review.
Usage:
  python3 spotai_cli.py --repo sample_repos/repo1_ecommerce_java --output-dir reports/repo1 --milestone 4
"""
import argparse
import os
import sys

if not getattr(sys, "frozen", False):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

try:
    from spotai.pipeline import SpotAIPipeline
    from spotai.github_pr_bot import GitHubPRReviewBot, GitHubPRPublishError
    from spotai.reporter import ReportExporter
    from spotai.repo_resolver import RepoResolver, RepoResolverError
except ImportError:
    from src.spotai.pipeline import SpotAIPipeline
    from src.spotai.github_pr_bot import GitHubPRReviewBot, GitHubPRPublishError
    from src.spotai.reporter import ReportExporter
    from src.spotai.repo_resolver import RepoResolver, RepoResolverError


def main():
    parser = argparse.ArgumentParser(
        description="SpotAI-Review: Static Code Analysis & AI Code Review Tool (SpotBugs + AST + Clone + LLM)"
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="Path to target Java/Python repository or remote Git/GitHub URL (e.g. https://github.com/user/repo)"
    )
    parser.add_argument("--output-dir", default="reports", help="Directory to write output reports")
    parser.add_argument("--clone-threshold", type=float, default=0.80, help="Clone similarity threshold (0.0 - 1.0)")
    parser.add_argument("--min-clone-lines", type=int, default=7, help="Minimum lines for clone detection")
    parser.add_argument("--max-cc", type=int, default=10, help="Cyclomatic Complexity warning threshold")
    parser.add_argument("--milestone", type=int, choices=[1, 2, 3, 4], default=4, help="Run mode matching project milestone (1..4)")
    parser.add_argument("--fail-on-gate", action="store_true", help="Exit with non-zero code if Quality Gate fails")
    parser.add_argument("--publish-pr-comment", action="store_true", help="Create or update the GitHub Actions bot's pull request summary")
    parser.add_argument(
        "--cleanup-temp",
        action="store_true",
        help="Automatically delete the temporary cloned directory after analysis completes"
    )
    parser.add_argument("--web", action="store_true", help="Launch SpotAI-Review FastAPI Web Application and UI")
    parser.add_argument("--port", type=int, default=8000, help="Port to run the web server on (default: 8000)")
    parser.add_argument("--host", default="127.0.0.1", help="Host address to bind the web server (default: 127.0.0.1)")
    args = parser.parse_args()

    if not 0 < args.clone_threshold <= 1 or args.min_clone_lines < 2 or args.max_cc < 1:
        parser.error("--clone-threshold must be within (0, 1], --min-clone-lines >= 2 and --max-cc >= 1")
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")

    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfig = getattr(stream, "reconfigure", None)
        if callable(reconfig):
            try:
                reconfig(encoding="utf-8", errors="replace")
            except Exception:
                pass

    if args.web:
        try:
            import uvicorn
            from spotai.web_server import app
        except ImportError as err:
            print(
                f"[WEB DEPENDENCY ERROR] {err}. "
                "Install Web dependencies with: python -m pip install -r requirements.txt",
                file=sys.stderr,
            )
            sys.exit(1)
        print("============================================================")
        print(f"   Starting SpotAI-Review Web Dashboard on http://{args.host}:{args.port}")
        print(f"   REST API and Interactive Docs: http://{args.host}:{args.port}/docs")
        print("============================================================")
        uvicorn.run(app, host=args.host, port=args.port)
        return

    if not args.repo:
        parser.print_help()
        print("\n[ERROR] Either --repo <path_or_url> or --web must be specified.", file=sys.stderr)
        sys.exit(1)

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

        if args.publish_pr_comment:
            try:
                published = pr_bot.post_to_github_if_configured(
                    report, os.path.join(args.output_dir, "pr_review_payload.json")
                )
            except GitHubPRPublishError as err:
                print(f"[PR PUBLISH ERROR] {err}", file=sys.stderr)
                sys.exit(1)
            if not published:
                print(
                    "[PR PUBLISH ERROR] Missing GITHUB_TOKEN, GITHUB_REPOSITORY, "
                    "or valid pull_request data in GITHUB_EVENT_PATH",
                    file=sys.stderr,
                )
                sys.exit(1)
            print("[PR PUBLISH] GitHub pull request summary created or updated")

        print(f"=== SpotAI-Review ({report.milestone_stage}) Summary for '{report.repository_name}' ===")
        print(f"Files Scanned : {report.files_scanned} ({report.total_loc} LOC)")
        print(f"Average CC    : {report.average_cc:.2f} | Max CC: {report.max_cc} | Avg MI: {report.average_mi:.1f}")
        print(f"Total Issues  : {len(report.issues)} -> By Engine: {report.summary_by_engine}")
        severities = {severity: sum(issue.severity == severity for issue in report.issues)
                      for severity in ("CRITICAL", "HIGH", "MEDIUM", "LOW")}
        print(f"By Severity   : {severities}")
        print(f"Engine Status : {report.engine_status}")
        print(f"Issues by Type: {report.summary_by_type}")
        print(f"Quality Gate  : {'PASSED' if report.quality_gate_passed else 'FAILED'}")
        print(f"Reports saved : {os.path.abspath(args.output_dir)}")

        if args.fail_on_gate and not report.quality_gate_passed:
            sys.exit(2)

    except (OSError, ValueError, RuntimeError) as err:
        print(f"[ANALYSIS ERROR] {err}", file=sys.stderr)
        sys.exit(1)

    finally:
        if is_temp and args.cleanup_temp and repo_dir:
            print(f"[INFO] Cleaning up temporary directory: {repo_dir}")
            resolver.cleanup(repo_dir)


if __name__ == "__main__":
    main()
