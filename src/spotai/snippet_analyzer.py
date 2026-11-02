"""
Snippet Analyzer Module (SOLID - Single Responsibility Principle)
Dedicated engine for analyzing isolated code snippets in real-time (Live Code Playground).
Supports both Java and Python snippets, computing McCabe CC, Cognitive Complexity,
Maintainability Index, detecting 8 Code Smells, and generating AI refactoring with stated limitations.
"""
import ast
import re
from typing import Any, Dict, List, Optional
from .models import CodeIssue, MethodMetric
from .ast_analyzer import ASTCodeSmellAnalyzer
from .ai_refactor import AIRefactoringEngine


class SnippetAnalyzer:
    """Analyzes raw Java or Python snippets in real-time for Live Code Playground."""

    def __init__(self, max_cc: int = 10, max_method_lines: int = 35):
        self.max_cc = max_cc
        self.max_method_lines = max_method_lines
        self.ast_analyzer = ASTCodeSmellAnalyzer(
            max_cc=self.max_cc,
            max_method_lines=self.max_method_lines
        )
        self.ai_engine = AIRefactoringEngine()

    def analyze_snippet(self, code: str, language: str) -> Dict[str, Any]:
        """
        Analyze a raw code string.
        Returns a dictionary containing status, complexity metrics, detected issues,
        and AI refactoring suggestions.
        """
        code_clean = (code or "").strip()
        if not code_clean:
            return {
                "status": "error",
                "message": "Source code is empty. Please enter Java or Python code to analyze.",
                "issues": [],
                "metrics": [],
                "summary": {}
            }

        lang = language.lower().strip()
        if lang not in ("python", "py", "java"):
            return {
                "status": "unsupported_language",
                "message": f"Language '{language}' is currently not supported in Playground. SpotAI-Review focuses on Java and Python.",
                "issues": [],
                "metrics": [],
                "summary": {}
            }

        if lang in ("python", "py"):
            return self._analyze_python_snippet(code_clean)
        else:
            return self._analyze_java_snippet(code_clean)

    def _analyze_python_snippet(self, code: str) -> Dict[str, Any]:
        # Validate Python syntax first
        try:
            ast.parse(code)
        except SyntaxError as e:
            return {
                "status": "syntax_error",
                "message": f"Python SyntaxError at line {e.lineno}: {e.msg}",
                "line": e.lineno,
                "offset": e.offset,
                "issues": [],
                "metrics": [],
                "summary": {"loc": len(code.splitlines()), "cc": 0, "mi": 0.0}
            }

        lines = code.splitlines()
        issues, metrics = self.ast_analyzer._analyze_python_file("playground.py", code, lines)

        # Calculate general LOC
        non_empty_lines = [ln for ln in lines if ln.strip() and not ln.strip().startswith("#")]
        total_loc = len(non_empty_lines)

        # If no methods were detected (e.g. script-level code), compute script-level CC & MI
        if not metrics:
            cc = 1
            for node in ast.walk(ast.parse(code)):
                if isinstance(node, (ast.If, ast.For, ast.While, ast.ExceptHandler, ast.With)):
                    cc += 1
                elif isinstance(node, ast.BoolOp):
                    cc += len(node.values) - 1
            mi = self.ast_analyzer._compute_maintainability_index(total_loc, cc, len(code.split()))
            metrics.append(
                MethodMetric(
                    file_path="playground.py",
                    class_name="Script",
                    method_name="main_script",
                    start_line=1,
                    end_line=len(lines),
                    loc=total_loc,
                    param_count=0,
                    max_nesting_depth=1,
                    cyclomatic_complexity=cc,
                    cognitive_complexity=cc - 1,
                    maintainability_index=mi
                )
            )

        # Enrich issues with AI Refactoring suggestions
        if issues:
            self.ai_engine.enrich_issues(issues)

        return self._format_response("python", code, lines, issues, metrics)

    def _analyze_java_snippet(self, code: str) -> Dict[str, Any]:
        lines = code.splitlines()
        is_wrapped = False
        original_line_offset = 0

        # If user pasted raw method(s) without class wrapper, wrap it for AST regex parser
        has_class = bool(re.search(r"\bclass\s+\w+", code))
        if not has_class:
            wrapped_code = f"public class PlaygroundSnippet {{\n{code}\n}}"
            lines = wrapped_code.splitlines()
            is_wrapped = True
            original_line_offset = 1  # 1-indexed wrapped header

        issues, metrics = self.ast_analyzer._analyze_java_file("PlaygroundSnippet.java", "\n".join(lines), lines)

        # Adjust line numbers back if wrapped
        if is_wrapped:
            for issue in issues:
                issue.start_line = max(1, issue.start_line - original_line_offset)
                issue.end_line = max(1, issue.end_line - original_line_offset)
            for m in metrics:
                m.start_line = max(1, m.start_line - original_line_offset)
                m.end_line = max(1, m.end_line - original_line_offset)

        # Enrich issues with AI Refactoring suggestions
        if issues:
            self.ai_engine.enrich_issues(issues)

        raw_lines = code.splitlines()
        return self._format_response("java", code, raw_lines, issues, metrics)

    def _format_response(
        self,
        lang: str,
        code: str,
        lines: List[str],
        issues: List[CodeIssue],
        metrics: List[MethodMetric]
    ) -> Dict[str, Any]:
        non_empty = [ln for ln in lines if ln.strip() and not ln.strip().startswith(("//", "#", "/*", "*"))]
        total_loc = len(non_empty)

        avg_cc = round(sum(m.cyclomatic_complexity for m in metrics) / max(1, len(metrics)), 2)
        max_cc = max((m.cyclomatic_complexity for m in metrics), default=1)
        avg_mi = round(sum(m.maintainability_index for m in metrics) / max(1, len(metrics)), 1)
        avg_cog = round(sum(m.cognitive_complexity for m in metrics) / max(1, len(metrics)), 1)

        serialized_issues = []
        for i in issues:
            serialized_issues.append({
                "issue_id": i.issue_id,
                "type": i.smell_or_bug_type,
                "category": i.category,
                "severity": i.severity,
                "message": i.message,
                "start_line": i.start_line,
                "end_line": i.end_line,
                "entity_name": i.entity_name,
                "code_snippet": i.code_snippet,
                "ai_explanation": i.ai_explanation,
                "ai_refactored_code": i.ai_refactored_code,
                "ai_limitations": i.ai_limitations,
                "verified_cc_after": i.verified_cc_after,
            })

        serialized_metrics = []
        for m in metrics:
            serialized_metrics.append({
                "method_name": m.method_name,
                "class_name": m.class_name,
                "loc": m.loc,
                "param_count": m.param_count,
                "cyclomatic_complexity": m.cyclomatic_complexity,
                "cognitive_complexity": m.cognitive_complexity,
                "maintainability_index": m.maintainability_index,
                "max_nesting_depth": m.max_nesting_depth
            })

        quality_passed = len([i for i in issues if i.severity in ("HIGH", "CRITICAL")]) == 0 and max_cc <= self.max_cc

        return {
            "status": "success",
            "language": lang,
            "summary": {
                "total_loc": total_loc,
                "issues_count": len(issues),
                "average_cc": avg_cc,
                "max_cc": max_cc,
                "average_mi": avg_mi,
                "average_cognitive": avg_cog,
                "quality_gate_passed": quality_passed
            },
            "metrics": serialized_metrics,
            "issues": serialized_issues
        }
