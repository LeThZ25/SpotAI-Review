from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any


@dataclass
class CodeIssue:
    issue_id: str
    source_engine: str          # "SpotBugs", "AST-Smell", or "Clone-Detector"
    category: str               # e.g., "BAD_PRACTICE", "SECURITY", "CODE_SMELL", "DUPLICATION"
    smell_or_bug_type: str      # e.g., "Long Method", "NP_NULL_ON_SOME_PATH", "Type-2 Code Clone"
    severity: str               # "HIGH", "MEDIUM", "LOW"
    file_path: str
    start_line: int
    end_line: int
    entity_name: str            # Method or Class name
    message: str
    cyclomatic_complexity: Optional[int] = None
    cognitive_complexity: Optional[int] = None
    code_snippet: str = ""
    clone_partner: Optional[str] = None
    similarity_score: Optional[float] = None
    # Populated in Milestone 2/3 by AI Refactoring Engine
    ai_explanation: Optional[str] = None
    ai_refactored_code: Optional[str] = None
    ai_limitations: Optional[str] = None
    ai_confidence: Optional[float] = None
    verified_cc_after: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MethodMetric:
    file_path: str
    class_name: str
    method_name: str
    start_line: int
    end_line: int
    loc: int
    param_count: int
    max_nesting_depth: int
    cyclomatic_complexity: int
    cognitive_complexity: int
    maintainability_index: float


@dataclass
class AnalysisReport:
    repository_name: str
    milestone_stage: str
    files_scanned: int
    total_loc: int
    average_cc: float
    max_cc: int
    average_mi: float
    quality_gate_passed: bool
    issues: List[CodeIssue] = field(default_factory=list)
    method_metrics: List[MethodMetric] = field(default_factory=list)
    summary_by_type: Dict[str, int] = field(default_factory=dict)
    summary_by_engine: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "repository_name": self.repository_name,
            "milestone_stage": self.milestone_stage,
            "files_scanned": self.files_scanned,
            "total_loc": self.total_loc,
            "average_cc": round(self.average_cc, 2),
            "max_cc": self.max_cc,
            "average_mi": round(self.average_mi, 2),
            "quality_gate_passed": self.quality_gate_passed,
            "summary_by_type": self.summary_by_type,
            "summary_by_engine": self.summary_by_engine,
            "issues": [i.to_dict() for i in self.issues],
            "method_metrics": [asdict(m) for m in self.method_metrics],
        }
