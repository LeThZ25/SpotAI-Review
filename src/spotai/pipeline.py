"""
Main Analysis Pipeline Orchestrator
Supports running by project milestone (--milestone 1|2|3|4) so the code execution matches
Group 4's progress reports from Week 4 through Final Submission.
"""
from collections import Counter
from typing import Optional
from .models import AnalysisReport
from .spotbugs_adapter import SpotBugsAdapter
from .ast_analyzer import ASTCodeSmellAnalyzer
from .clone_detector import CloneDetector
from .ai_refactor import AIRefactoringEngine


class SpotAIPipeline:
    def __init__(
        self,
        clone_threshold: float = 0.80,
        min_clone_lines: int = 7,
        max_cc: int = 10,
        max_method_lines: int = 35,
        milestone: int = 4,
    ):
        self.clone_threshold = clone_threshold
        self.min_clone_lines = min_clone_lines
        self.max_cc = max_cc
        self.max_method_lines = max_method_lines
        self.milestone = milestone

    def analyze(self, repo_root: str, repo_name: Optional[str] = None) -> AnalysisReport:
        import os
        rname = repo_name or os.path.basename(os.path.abspath(repo_root))

        # Milestone 1+: SpotBugs XML Adapter + AST Code Smells & Cyclomatic Complexity
        sb_adapter = SpotBugsAdapter(repo_root)
        sb_issues = sb_adapter.run_or_load()

        ast_engine = ASTCodeSmellAnalyzer(
            max_method_lines=self.max_method_lines,
            max_cc=self.max_cc,
        )
        ast_issues, method_metrics, files_scanned, total_loc = ast_engine.analyze_repository(repo_root)

        all_issues = sb_issues + ast_issues

        # Milestone 2+: Configurable Clone Detector + AI Refactoring Engine
        if self.milestone >= 2:
            clone_engine = CloneDetector(
                similarity_threshold=self.clone_threshold,
                min_lines=self.min_clone_lines,
            )
            clone_issues = clone_engine.detect_clones(repo_root)
            all_issues.extend(clone_issues)

            ai_engine = AIRefactoringEngine()
            ai_engine.enrich_issues(all_issues)

        avg_cc = (
            sum(m.cyclomatic_complexity for m in method_metrics) / len(method_metrics)
            if method_metrics
            else 1.0
        )
        max_cc_val = max((m.cyclomatic_complexity for m in method_metrics), default=1)
        avg_mi = (
            sum(m.maintainability_index for m in method_metrics) / len(method_metrics)
            if method_metrics
            else 85.0
        )

        high_count = sum(1 for i in all_issues if i.severity == "HIGH")
        quality_gate_passed = high_count == 0 and max_cc_val <= self.max_cc

        by_type = dict(Counter(i.smell_or_bug_type for i in all_issues))
        by_engine = dict(Counter(i.source_engine for i in all_issues))

        return AnalysisReport(
            repository_name=rname,
            milestone_stage=f"Milestone-{self.milestone}",
            files_scanned=files_scanned,
            total_loc=total_loc,
            average_cc=avg_cc,
            max_cc=max_cc_val,
            average_mi=avg_mi,
            quality_gate_passed=quality_gate_passed,
            issues=all_issues,
            method_metrics=method_metrics,
            summary_by_type=by_type,
            summary_by_engine=by_engine,
        )
