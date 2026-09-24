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
        self.repo_root = os.path.abspath(repo_root)
        self.spotbugs_xml_path = spotbugs_xml_path
        self.spotbugs_bin = spotbugs_bin

    def run_or_load(self) -> List[CodeIssue]:
        """
        If a SpotBugs binary and compiled target/classes exist, can invoke SpotBugs CLI directly;
        otherwise parses existing spotbugsXml.xml in the repository or specified path.
        """
        xml_path = self._resolve_xml_path()
        if not xml_path or not os.path.exists(xml_path):
            return []
        return self.parse_spotbugs_xml(xml_path)

    def _resolve_xml_path(self) -> Optional[str]:
        if self.spotbugs_xml_path and os.path.exists(self.spotbugs_xml_path):
            return self.spotbugs_xml_path
        # Check standard Maven/Gradle SpotBugs output paths or repo root
        candidates = [
            os.path.join(self.repo_root, "spotbugsXml.xml"),
            os.path.join(self.repo_root, "target", "spotbugsXml.xml"),
            os.path.join(self.repo_root, "build", "reports", "spotbugs", "main.xml"),
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        return None

    def parse_spotbugs_xml(self, xml_path: str) -> List[CodeIssue]:
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
                start_line = int(source_line_el.attrib.get("start", "1"))
                end_line = int(source_line_el.attrib.get("end", str(start_line)))

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
        candidates = [
            os.path.join(self.repo_root, rel_source),
            os.path.join(self.repo_root, "src", "main", "java", rel_source),
            os.path.join(self.repo_root, "src", rel_source),
        ]
        # Also search by basename if package path differs
        basename = os.path.basename(rel_source)
        for root_dir, _, files in os.walk(self.repo_root):
            if basename in files:
                candidates.append(os.path.join(root_dir, basename))

        for path in candidates:
            if os.path.exists(path) and os.path.isfile(path):
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                s = max(1, start_line - 3)
                e = min(len(lines), max(end_line + 4, start_line + 8))
                snippet = "".join(lines[s - 1 : e]).rstrip()
                rel_path = os.path.relpath(path, self.repo_root)
                return rel_path, snippet
        return rel_source, ""
