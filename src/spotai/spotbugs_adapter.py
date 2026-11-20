"""
Module 1: SpotBugs XML & CLI Adapter (Adapter Design Pattern)
Owner: Duong Le Thuong (DTC235340030)
Integrates SpotBugs bytecode analysis reports (spotbugsXml.xml) with source-level code extraction
so that AI Refactoring can explain and fix bytecode bugs detected by SpotBugs.
"""
import os
import subprocess
import xml.etree.ElementTree as ET
from typing import List, Optional
from .models import CodeIssue


PRIORITY_TO_SEVERITY = {
    "1": "HIGH",
    "2": "MEDIUM",
    "3": "LOW",
}


class SpotBugsAdapter:
    def __init__(self, repo_root: str, spotbugs_xml_path: Optional[str] = None, spotbugs_bin: Optional[str] = None):
        self.repo_root = os.path.realpath(repo_root)
        self.spotbugs_xml_path = spotbugs_xml_path
        self.spotbugs_bin = spotbugs_bin
        self.status = "not_available"

    def _within_repo(self, path: str) -> bool:
        try:
            return os.path.commonpath((self.repo_root, os.path.realpath(path))) == self.repo_root
        except ValueError:
            return False

    def run_or_load(self) -> List[CodeIssue]:
        """
        If a SpotBugs binary and compiled target/classes exist, can invoke SpotBugs CLI directly;
        otherwise parses existing spotbugsXml.xml in the repository or specified path.
        """
        try:
            xml_path = self._resolve_xml_path()
        except ValueError as exc:
            self.status = "error"
            return [CodeIssue(
                issue_id="SB-ERROR", source_engine="SpotBugs", category="ANALYSIS",
                smell_or_bug_type="ANALYSIS_ERROR", severity="HIGH",
                file_path="spotbugsXml.xml", start_line=1, end_line=1,
                entity_name="SpotBugs XML", message=str(exc),
            )]
        if not xml_path:
            return []
        try:
            result = self.parse_spotbugs_xml(xml_path)
            self.status = "loaded"
            return result
        except (ET.ParseError, OSError, ValueError) as exc:
            self.status = "error"
            return [CodeIssue(
                issue_id="SB-ERROR", source_engine="SpotBugs", category="ANALYSIS",
                smell_or_bug_type="ANALYSIS_ERROR", severity="HIGH",
                file_path=os.path.relpath(xml_path, self.repo_root), start_line=1, end_line=1,
                entity_name="SpotBugs XML", message=f"Unable to parse SpotBugs report: {exc}",
            )]

    def _resolve_xml_path(self) -> Optional[str]:
        if self.spotbugs_xml_path:
            if not self._within_repo(self.spotbugs_xml_path):
                raise ValueError("SpotBugs XML must be inside repository")
            return self.spotbugs_xml_path if os.path.isfile(self.spotbugs_xml_path) else None
        # Check standard Maven/Gradle SpotBugs output paths or repo root
        candidates = [
            os.path.join(self.repo_root, "spotbugsXml.xml"),
            os.path.join(self.repo_root, "target", "spotbugsXml.xml"),
            os.path.join(self.repo_root, "build", "reports", "spotbugs", "main.xml"),
        ]
        for c in candidates:
            if self._within_repo(c) and os.path.isfile(c):
                return c
        return None

    def parse_spotbugs_xml(self, xml_path: str) -> List[CodeIssue]:
        if not self._within_repo(xml_path):
            raise ValueError("SpotBugs XML must be inside repository")
        issues: List[CodeIssue] = []
        tree = ET.parse(xml_path)
        root = tree.getroot()
        idx = 1
        for bug in root.findall("BugInstance"):
            bug_type = bug.attrib.get("type", "UNKNOWN_BUG")
            category = bug.attrib.get("category", "CORRECTNESS")
            priority = bug.attrib.get("priority", "2")
            severity = PRIORITY_TO_SEVERITY.get(priority, "MEDIUM")

            long_msg_el = bug.find("LongMessage")
            short_msg_el = bug.find("ShortMessage")
            message = (
                long_msg_el.text.strip()
                if long_msg_el is not None and long_msg_el.text
                else (short_msg_el.text.strip() if short_msg_el is not None and short_msg_el.text else bug_type)
            )

            class_el = bug.find("Class")
            method_el = bug.find("Method")
            source_line_el = bug.find("SourceLine")
            if source_line_el is None and method_el is not None:
                source_line_el = method_el.find("SourceLine")
            if source_line_el is None and class_el is not None:
                source_line_el = class_el.find("SourceLine")

            rel_source = "Unknown.java"
            start_line = 1
            end_line = 1
            if source_line_el is not None:
                rel_source = source_line_el.attrib.get("sourcepath", rel_source)
                try:
                    start_line = max(1, int(source_line_el.attrib.get("start", "1")))
                    end_line = max(start_line, int(source_line_el.attrib.get("end", str(start_line))))
                except ValueError:
                    start_line = end_line = 1

            entity_name = ""
            if class_el is not None:
                entity_name = class_el.attrib.get("classname", "")
            if method_el is not None:
                mname = method_el.attrib.get("name", "")
                entity_name = f"{entity_name}.{mname}()" if entity_name else mname

            resolved_file, snippet = self._extract_source_snippet(rel_source, start_line, end_line)
            issues.append(
                CodeIssue(
                    issue_id=f"SB-{idx:03d}",
                    source_engine="SpotBugs",
                    category=f"SPOTBUGS_{category}",
                    smell_or_bug_type=bug_type,
                    severity=severity,
                    file_path=resolved_file,
                    start_line=start_line,
                    end_line=end_line,
                    entity_name=entity_name or rel_source,
                    message=f"[SpotBugs {bug_type}] {message}",
                    code_snippet=snippet,
                )
            )
            idx += 1
        return issues

    def _extract_source_snippet(self, rel_source: str, start_line: int, end_line: int):
        if (os.path.isabs(rel_source) or "\\" in rel_source
                or any(part == ".." for part in rel_source.split("/"))
                or ":" in rel_source):
            return "Unknown.java", ""
        candidates = [
            os.path.join(self.repo_root, rel_source),
            os.path.join(self.repo_root, "src", "main", "java", rel_source),
            os.path.join(self.repo_root, "src", rel_source),
        ]
        # Also search by basename if package path differs
        basename = os.path.basename(rel_source)
        for root_dir, dirs, files in os.walk(self.repo_root):
            dirs[:] = [d for d in dirs if self._within_repo(os.path.join(root_dir, d))]
            if basename in files:
                candidates.append(os.path.join(root_dir, basename))

        for path in candidates:
            if self._within_repo(path) and os.path.isfile(path):
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()
                except OSError:
                    continue
                s = max(1, start_line - 3)
                e = min(len(lines), max(end_line + 4, start_line + 8))
                snippet = "".join(lines[s - 1 : e]).rstrip()
                rel_path = os.path.relpath(path, self.repo_root)
                return rel_path, snippet
        return rel_source, ""
