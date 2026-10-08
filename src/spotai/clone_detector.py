"""
Module 3: Configurable Duplicate Code (Clone) Detector
Owner: Duong Quoc Toan (DTC235210055)
Detects Type-1 (Exact), Type-2 (Renamed Identifiers/Literals), and Type-3 (Near-Miss)
duplicated code blocks across a repository with user-configurable similarity threshold
and minimum block size.
"""
import difflib
import os
import re
from dataclasses import dataclass
from typing import List
from .models import CodeIssue


@dataclass
class NormalizedBlock:
    file_path: str
    entity_name: str
    start_line: int
    end_line: int
    raw_code: str
    normalized_text: str


JAVA_PY_KEYWORDS = {
    "if", "else", "for", "while", "return", "switch", "case", "break", "continue",
    "try", "catch", "finally", "throw", "throws", "new", "public", "private",
    "protected", "static", "final", "void", "int", "double", "float", "boolean",
    "String", "List", "Map", "def", "class", "import", "from", "and", "or", "not",
    "in", "is", "None", "True", "False", "null", "true", "false"
}


class CloneDetector:
    def __init__(self, similarity_threshold: float = 0.80, min_lines: int = 8):
        self.similarity_threshold = similarity_threshold
        self.min_lines = min_lines

    @staticmethod
    def normalize_code(code: str) -> str:
        # Strip comments
        code = re.sub(r"//.*?$|#.*?$", "", code, flags=re.MULTILINE)
        code = re.sub(r"/\*.*?\*/", "", code, flags=re.DOTALL)
        # Replace string literals and numbers
        code = re.sub(r"\".*?\"|'.*?'", "$STR", code)
        code = re.sub(r"\b\d+(?:\.\d+)?\b", "$NUM", code)

        # Normalize identifiers to $ID while preserving language keywords
        def repl_ident(match):
            tok = match.group(0)
            return tok if tok in JAVA_PY_KEYWORDS else "$ID"

        code = re.sub(r"\b[A-Za-z_]\w*\b", repl_ident, code)
        # Collapse whitespace
        lines = [re.sub(r"\s+", " ", ln).strip() for ln in code.splitlines()]
        lines = [ln for ln in lines if ln and ln not in {"{", "}"}]
        return "\n".join(lines)

    def detect_clones(self, repo_root: str) -> List[CodeIssue]:
        blocks = self._extract_candidate_blocks(repo_root)
        issues: List[CodeIssue] = []
        seen_pairs = set()
        clone_idx = 1

        for i in range(len(blocks)):
            for j in range(i + 1, len(blocks)):
                b1, b2 = blocks[i], blocks[j]
                if b1.file_path == b2.file_path and abs(b1.start_line - b2.start_line) < self.min_lines:
                    continue
                pair_key = (b1.file_path, b1.start_line, b2.file_path, b2.start_line)
                if pair_key in seen_pairs:
                    continue

                sim = difflib.SequenceMatcher(None, b1.normalized_text, b2.normalized_text).ratio()
                if sim >= self.similarity_threshold:
                    seen_pairs.add(pair_key)
                    clone_type = "Type-1 Exact Clone" if b1.raw_code.strip() == b2.raw_code.strip() else (
                        "Type-2 Renamed Clone" if sim >= 0.94 else "Type-3 Near-Miss Clone"
                    )
                    issues.append(
                        CodeIssue(
                            issue_id=f"CLN-{clone_idx:03d}",
                            source_engine="Clone-Detector",
                            category="DUPLICATION",
                            smell_or_bug_type="Duplicated Code",
                            severity="HIGH" if sim >= 0.90 else "MEDIUM",
                            file_path=b1.file_path,
                            start_line=b1.start_line,
                            end_line=b1.end_line,
                            entity_name=b1.entity_name,
                            message=(
                                f"{clone_type} detected ({sim * 100:.1f}% structural similarity >= "
                                f"{self.similarity_threshold * 100:.0f}% threshold) between "
                                f"'{b1.entity_name}' ({b1.file_path}:{b1.start_line}-{b1.end_line}) and "
                                f"'{b2.entity_name}' ({b2.file_path}:{b2.start_line}-{b2.end_line})."
                            ),
                            code_snippet=b1.raw_code,
                            clone_partner=f"{b2.file_path}:{b2.start_line}-{b2.end_line} ({b2.entity_name})",
                            similarity_score=round(sim, 3),
                        )
                    )
                    clone_idx += 1

        return issues

    def _extract_candidate_blocks(self, repo_root: str) -> List[NormalizedBlock]:
        blocks: List[NormalizedBlock] = []
        java_method_re = re.compile(
            r"^\s*(?:public|protected|private|static|final|synchronized|\s)+[\w\<\>\[\],\s]+\s+(\w+)\s*\([^\)]*\)\s*(?:throws\s+[\w,\s]+)?\{"
        )

        for root, dirs, files in os.walk(repo_root):
            dirs[:] = [
                d for d in dirs
                if d not in {".git", "__pycache__", "node_modules", "target", "build", ".venv", "venv", "env", ".idea", ".vscode", "dist", ".gradle"}
            ]
            for fname in sorted(files):
                if not (fname.endswith(".java") or fname.endswith(".py")):
                    continue
                full_path = os.path.join(root, fname)
                rel_path = os.path.relpath(full_path, repo_root)
                with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                    source = f.read()
                lines = source.splitlines()

                if fname.endswith(".java"):
                    for idx, line in enumerate(lines):
                        m = java_method_re.match(line)
                        if not m:
                            continue
                        mname = m.group(1)
                        if mname in {"if", "for", "while", "switch", "catch"}:
                            continue
                        end_idx = self._find_brace_end(lines, idx)
                        # Exclude signature line so renamed methods with identical bodies get compared accurately
                        body_lines = lines[idx + 1 : end_idx]
                        if len(body_lines) >= self.min_lines:
                            raw = "\n".join(lines[idx : end_idx + 1])
                            norm = self.normalize_code("\n".join(body_lines))
                            if len(norm.splitlines()) >= self.min_lines - 2:
                                blocks.append(
                                    NormalizedBlock(
                                        file_path=rel_path,
                                        entity_name=mname,
                                        start_line=idx + 1,
                                        end_line=end_idx + 1,
                                        raw_code=raw,
                                        normalized_text=norm,
                                    )
                                )
                elif fname.endswith(".py"):
                    import ast
                    try:
                        tree = ast.parse(source)
                        for node in ast.walk(tree):
                            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                s = node.lineno
                                e = getattr(node, "end_lineno", s + 10)
                                if (e - s) >= self.min_lines:
                                    raw = "\n".join(lines[s - 1 : e])
                                    body_raw = "\n".join(lines[s : e])
                                    norm = self.normalize_code(body_raw)
                                    blocks.append(
                                        NormalizedBlock(
                                            file_path=rel_path,
                                            entity_name=node.name,
                                            start_line=s,
                                            end_line=e,
                                            raw_code=raw,
                                            normalized_text=norm,
                                        )
                                    )
                    except SyntaxError:
                        pass

        return blocks

    @staticmethod
    def _find_brace_end(lines: List[str], start_idx: int) -> int:
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
