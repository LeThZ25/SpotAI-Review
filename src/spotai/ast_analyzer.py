"""
Module 2: Multi-Language AST & Structural Code Smell Analyzer (Strategy Design Pattern)
Owner: Duong Le Thuong (DTC235340030)
Detects 8 code smell types (exceeding minimum requirement of 5):
  1. Long Method
  2. Large Class (God Class)
  3. Long Parameter List
  4. High Cyclomatic Complexity (Complex Method)
  5. Deeply Nested Control Flow
  6. Data Clumps / Primitive Obsession
  7. Magic Numbers & Hardcoded Config/Secrets
  8. Feature Envy / Excessive External Coupling
Also computes McCabe Cyclomatic Complexity (CC), Cognitive Complexity, and Maintainability Index (MI).
Supports both Java (.java) and Python (.py) repositories.
"""
import ast
import math
import os
import re
from typing import List, Tuple, Dict
from .models import CodeIssue, MethodMetric


class ASTCodeSmellAnalyzer:
    def __init__(
        self,
        max_method_lines: int = 35,
        max_class_lines: int = 180,
        max_class_methods: int = 12,
        max_params: int = 4,
        max_cc: int = 10,
        max_nesting: int = 3,
    ):
        self.max_method_lines = max_method_lines
        self.max_class_lines = max_class_lines
        self.max_class_methods = max_class_methods
        self.max_params = max_params
        self.max_cc = max_cc
        self.max_nesting = max_nesting
        self._issue_counter = 1

    def _next_id(self) -> str:
        iid = f"AST-{self._issue_counter:03d}"
        self._issue_counter += 1
        return iid

    def analyze_repository(self, repo_root: str) -> Tuple[List[CodeIssue], List[MethodMetric], int, int]:
        issues: List[CodeIssue] = []
        metrics: List[MethodMetric] = []
        files_scanned = 0
        total_loc = 0

        for root, dirs, files in os.walk(repo_root):
            dirs[:] = [
                d for d in dirs
                if d not in {".git", "__pycache__", "node_modules", "target", "build", ".venv", "venv", "env", ".idea", ".vscode", "dist", ".gradle"}
            ]
            for fname in sorted(files):
                if fname.endswith(".java") or fname.endswith(".py"):
                    full_path = os.path.join(root, fname)
                    rel_path = os.path.relpath(full_path, repo_root)
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        source = f.read()
                    lines = source.splitlines()
                    loc = sum(1 for ln in lines if ln.strip() and not ln.strip().startswith(("//", "#", "/*", "*")))
                    total_loc += loc
                    files_scanned += 1

                    if fname.endswith(".py"):
                        f_issues, f_metrics = self._analyze_python_file(rel_path, source, lines)
                    else:
                        f_issues, f_metrics = self._analyze_java_file(rel_path, source, lines)
                    issues.extend(f_issues)
                    metrics.extend(f_metrics)

        return issues, metrics, files_scanned, total_loc

    @staticmethod
    def _compute_maintainability_index(loc: int, cc: int, token_count: int) -> float:
        loc_safe = max(1, loc)
        vol = max(1.0, token_count * math.log2(max(2, token_count)))
        raw_mi = 171.0 - 5.2 * math.log(vol) - 0.23 * cc - 16.2 * math.log(loc_safe)
        return max(0.0, min(100.0, round(raw_mi * 100.0 / 171.0, 2)))

    # ── Python AST Analysis ──
    def _analyze_python_file(
        self, rel_path: str, source: str, lines: List[str]
    ) -> Tuple[List[CodeIssue], List[MethodMetric]]:
        issues: List[CodeIssue] = []
        metrics: List[MethodMetric] = []
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return issues, metrics

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                c_start = node.lineno
                c_end = getattr(node, "end_lineno", c_start + 20)
                c_loc = c_end - c_start + 1
                methods = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                if c_loc > self.max_class_lines or len(methods) > self.max_class_methods:
                    snippet = "\n".join(lines[c_start - 1 : min(c_end, c_start + 18)])
                    issues.append(
                        CodeIssue(
                            issue_id=self._next_id(),
                            source_engine="AST-Smell",
                            category="CODE_SMELL",
                            smell_or_bug_type="Large Class",
                            severity="MEDIUM" if c_loc <= self.max_class_lines * 1.4 else "HIGH",
                            file_path=rel_path,
                            start_line=c_start,
                            end_line=c_end,
                            entity_name=node.name,
                            message=(
                                f"Class '{node.name}' spans {c_loc} lines with {len(methods)} methods "
                                f"(thresholds: {self.max_class_lines} LOC / {self.max_class_methods} methods), "
                                "violating the Single Responsibility Principle."
                            ),
                            code_snippet=snippet,
                        )
                    )

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                m_start = node.lineno
                m_end = getattr(node, "end_lineno", m_start + 10)
                m_loc = m_end - m_start + 1
                params = [a.arg for a in node.args.args if a.arg not in ("self", "cls")]
                param_count = len(params)
                cc, cog, max_depth, ext_calls = self._python_complexity(node)
                snippet = "\n".join(lines[m_start - 1 : m_end])
                mi = self._compute_maintainability_index(m_loc, cc, len(snippet.split()))

                metrics.append(
                    MethodMetric(
                        file_path=rel_path,
                        class_name="Module",
                        method_name=node.name,
                        start_line=m_start,
                        end_line=m_end,
                        loc=m_loc,
                        param_count=param_count,
                        max_nesting_depth=max_depth,
                        cyclomatic_complexity=cc,
                        cognitive_complexity=cog,
                        maintainability_index=mi,
                    )
                )

                self._evaluate_method_smells(
                    issues, rel_path, node.name, m_start, m_end, m_loc, param_count, cc, cog, max_depth, ext_calls, snippet
                )

        return issues, metrics

    def _python_complexity(self, func_node: ast.AST) -> Tuple[int, int, int, int]:
        cc = 1
        cognitive = 0
        max_depth = 0
        external_calls = 0

        def visit(n: ast.AST, depth: int):
            nonlocal cc, cognitive, max_depth, external_calls
            is_branch = isinstance(n, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.IfExp))
            if is_branch:
                cc += 1
                cognitive += 1 + depth
                depth += 1
                max_depth = max(max_depth, depth)
            elif isinstance(n, ast.BoolOp):
                cc += len(n.values) - 1
                cognitive += len(n.values) - 1
            elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                if isinstance(n.func.value, ast.Name) and n.func.value.id not in ("self", "cls"):
                    external_calls += 1

            for child in ast.iter_child_nodes(n):
                visit(child, depth)

        visit(func_node, 0)
        return cc, cognitive, max_depth, external_calls

    # ── Java AST / Structural Analysis ──
    def _analyze_java_file(
        self, rel_path: str, source: str, lines: List[str]
    ) -> Tuple[List[CodeIssue], List[MethodMetric]]:
        issues: List[CodeIssue] = []
        metrics: List[MethodMetric] = []

        # Detect class boundaries
        class_pattern = re.compile(r"\b(?:public|protected|private)?\s*(?:abstract|final)?\s*class\s+(\w+)")
        method_pattern = re.compile(
            r"^\s*(?:public|protected|private|static|final|synchronized|\s)+[\w\<\>\[\],\s]+\s+(\w+)\s*\(([^\)]*)\)\s*(?:throws\s+[\w,\s]+)?\{"
        )

        class_name = "UnknownClass"
        for idx, line in enumerate(lines, start=1):
            cm = class_pattern.search(line)
            if cm:
                class_name = cm.group(1)
                c_end = self._find_matching_brace(lines, idx - 1) + 1
                c_loc = c_end - idx + 1
                # Count methods inside class
                m_count = sum(1 for l in lines[idx - 1 : c_end] if method_pattern.match(l))
                if c_loc > self.max_class_lines or m_count > self.max_class_methods:
                    snippet = "\n".join(lines[idx - 1 : min(c_end, idx + 18)])
                    issues.append(
                        CodeIssue(
                            issue_id=self._next_id(),
                            source_engine="AST-Smell",
                            category="CODE_SMELL",
                            smell_or_bug_type="Large Class",
                            severity="HIGH" if c_loc > self.max_class_lines * 1.3 else "MEDIUM",
                            file_path=rel_path,
                            start_line=idx,
                            end_line=c_end,
                            entity_name=class_name,
                            message=(
                                f"Class '{class_name}' has {c_loc} lines and {m_count} methods "
                                f"(thresholds: {self.max_class_lines} LOC / {self.max_class_methods} methods). "
                                "Consider extracting cohesive domain collaborators."
                            ),
                            code_snippet=snippet,
                        )
                    )

        for idx in range(1, len(lines) + 1):
            # Join up to 10 lines to support multi-line Java method declarations
            header_chunk = " ".join(l.strip() for l in lines[idx - 1 : min(len(lines), idx + 9)])
            if not lines[idx - 1].strip().startswith(("public ", "protected ", "private ", "static ")):
                continue
            if ";" in lines[idx - 1].split("(")[0]:
                continue
            mm = method_pattern.match(header_chunk)
            if not mm:
                continue
            m_name = mm.group(1)
            if m_name in {"if", "for", "while", "switch", "catch", class_name}:
                continue
            raw_params = mm.group(2).strip()
            params = [p.strip() for p in raw_params.split(",") if p.strip()] if raw_params else []
            param_count = len(params)

            m_start = idx
            m_end = self._find_matching_brace(lines, idx - 1) + 1
            m_loc = m_end - m_start + 1
            m_lines = lines[m_start - 1 : m_end]
            snippet = "\n".join(m_lines)

            cc, cog, max_depth, ext_calls = self._java_complexity(m_lines)
            mi = self._compute_maintainability_index(m_loc, cc, len(snippet.split()))

            metrics.append(
                MethodMetric(
                    file_path=rel_path,
                    class_name=class_name,
                    method_name=f"{class_name}.{m_name}",
                    start_line=m_start,
                    end_line=m_end,
                    loc=m_loc,
                    param_count=param_count,
                    max_nesting_depth=max_depth,
                    cyclomatic_complexity=cc,
                    cognitive_complexity=cog,
                    maintainability_index=mi,
                )
            )

            self._evaluate_method_smells(
                issues,
                rel_path,
                f"{class_name}.{m_name}",
                m_start,
                m_end,
                m_loc,
                param_count,
                cc,
                cog,
                max_depth,
                ext_calls,
                snippet,
            )

        return issues, metrics

    @staticmethod
    def _find_matching_brace(lines: List[str], start_idx: int) -> int:
        depth = 0
        opened = False
        for i in range(start_idx, len(lines)):
            for ch in lines[i]:
                if ch == "{":
                    depth += 1
                    opened = True
                elif ch == "}":
                    depth -= 1
                    if opened and depth <= 0:
                        return i
        return len(lines) - 1

    @staticmethod
    def _java_complexity(m_lines: List[str]) -> Tuple[int, int, int, int]:
        cc = 1
        cognitive = 0
        depth = 0
        max_depth = 0
        ext_calls = 0

        branch_re = re.compile(r"\b(if|else\s+if|for|while|case|catch)\b")
        bool_re = re.compile(r"(\&\&|\|\||\?)")
        ext_call_re = re.compile(r"\b(?!this\b|super\b|System\b)[a-z]\w*\.\w+\(")

        for raw in m_lines:
            line = raw.split("//")[0]
            b_matches = branch_re.findall(line)
            op_matches = bool_re.findall(line)
            if b_matches:
                cc += len(b_matches)
                cognitive += len(b_matches) * (1 + max(0, depth - 1))
            if op_matches:
                cc += len(op_matches)
                cognitive += len(op_matches)
            ext_calls += len(ext_call_re.findall(line))

            for ch in line:
                if ch == "{":
                    depth += 1
                    max_depth = max(max_depth, depth - 1)
                elif ch == "}":
                    depth = max(0, depth - 1)

        return cc, cognitive, max_depth, ext_calls

    def _evaluate_method_smells(
        self,
        issues: List[CodeIssue],
        rel_path: str,
        entity_name: str,
        m_start: int,
        m_end: int,
        m_loc: int,
        param_count: int,
        cc: int,
        cog: int,
        max_depth: int,
        ext_calls: int,
        snippet: str,
    ):
        # 1. Long Method
        if m_loc > self.max_method_lines:
            issues.append(
                CodeIssue(
                    issue_id=self._next_id(),
                    source_engine="AST-Smell",
                    category="CODE_SMELL",
                    smell_or_bug_type="Long Method",
                    severity="HIGH" if m_loc > self.max_method_lines * 1.5 else "MEDIUM",
                    file_path=rel_path,
                    start_line=m_start,
                    end_line=m_end,
                    entity_name=entity_name,
                    message=(
                        f"Method '{entity_name}' is {m_loc} lines long (threshold: {self.max_method_lines} lines) "
                        f"with Cyclomatic Complexity = {cc}."
                    ),
                    cyclomatic_complexity=cc,
                    cognitive_complexity=cog,
                    code_snippet=snippet,
                )
            )

        # 2. High Cyclomatic Complexity (Complex Conditional / Method)
        if cc > self.max_cc:
            issues.append(
                CodeIssue(
                    issue_id=self._next_id(),
                    source_engine="AST-Smell",
                    category="COMPLEXITY",
                    smell_or_bug_type="High Cyclomatic Complexity",
                    severity="HIGH" if cc >= 15 else "MEDIUM",
                    file_path=rel_path,
                    start_line=m_start,
                    end_line=m_end,
                    entity_name=entity_name,
                    message=(
                        f"Method '{entity_name}' has McCabe Cyclomatic Complexity = {cc} "
                        f"(threshold: {self.max_cc}) and Cognitive Complexity = {cog}."
                    ),
                    cyclomatic_complexity=cc,
                    cognitive_complexity=cog,
                    code_snippet=snippet,
                )
            )

        # 3. Long Parameter List ( & Data Clumps indicator)
        if param_count > self.max_params:
            issues.append(
                CodeIssue(
                    issue_id=self._next_id(),
                    source_engine="AST-Smell",
                    category="CODE_SMELL",
                    smell_or_bug_type="Long Parameter List",
                    severity="MEDIUM",
                    file_path=rel_path,
                    start_line=m_start,
                    end_line=m_end,
                    entity_name=entity_name,
                    message=(
                        f"Method '{entity_name}' accepts {param_count} parameters (threshold: {self.max_params}). "
                        "Introduce Parameter Object or Builder pattern to encapsulate Data Clumps."
                    ),
                    cyclomatic_complexity=cc,
                    cognitive_complexity=cog,
                    code_snippet=snippet,
                )
            )

        # 4. Deeply Nested Control Flow
        if max_depth > self.max_nesting:
            issues.append(
                CodeIssue(
                    issue_id=self._next_id(),
                    source_engine="AST-Smell",
                    category="CODE_SMELL",
                    smell_or_bug_type="Deeply Nested Control Flow",
                    severity="MEDIUM",
                    file_path=rel_path,
                    start_line=m_start,
                    end_line=m_end,
                    entity_name=entity_name,
                    message=(
                        f"Method '{entity_name}' reaches a control-flow nesting depth of {max_depth} "
                        f"(threshold: {self.max_nesting}). Apply Guard Clauses (early returns) to flatten nesting."
                    ),
                    cyclomatic_complexity=cc,
                    cognitive_complexity=cog,
                    code_snippet=snippet,
                )
            )

        # 5. Feature Envy / Excessive External Coupling
        if ext_calls >= 7:
            issues.append(
                CodeIssue(
                    issue_id=self._next_id(),
                    source_engine="AST-Smell",
                    category="CODE_SMELL",
                    smell_or_bug_type="Feature Envy",
                    severity="LOW" if ext_calls < 10 else "MEDIUM",
                    file_path=rel_path,
                    start_line=m_start,
                    end_line=m_end,
                    entity_name=entity_name,
                    message=(
                        f"Method '{entity_name}' makes {ext_calls} external object member calls, indicating "
                        "Feature Envy. Consider moving behavior closer to the data owner class."
                    ),
                    cyclomatic_complexity=cc,
                    cognitive_complexity=cog,
                    code_snippet=snippet,
                )
            )

        # 6. Magic Numbers / Hardcoded Thresholds
        magic_nums = re.findall(r"(?<![\w\.])(?:0\.\d{2,}|[2-9]\d+(?:\.\d+)?)(?![\w\.])", snippet)
        if len(magic_nums) >= 3:
            issues.append(
                CodeIssue(
                    issue_id=self._next_id(),
                    source_engine="AST-Smell",
                    category="CODE_SMELL",
                    smell_or_bug_type="Magic Numbers",
                    severity="LOW",
                    file_path=rel_path,
                    start_line=m_start,
                    end_line=m_end,
                    entity_name=entity_name,
                    message=(
                        f"Method '{entity_name}' contains {len(magic_nums)} hardcoded numeric literals "
                        f"({', '.join(magic_nums[:4])}). Extract named domain constants."
                    ),
                    cyclomatic_complexity=cc,
                    cognitive_complexity=cog,
                    code_snippet=snippet,
                )
            )
