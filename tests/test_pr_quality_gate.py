"""Tests for PR regression gating without changing the repository-wide thresholds."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from spotai.models import AnalysisReport, CodeIssue, MethodMetric
from spotai.pr_quality_gate import apply_incremental_quality_gate


def make_report(issues=None, complexity=12):
    return AnalysisReport(
        repository_name="repo", milestone_stage="Milestone-4", files_scanned=1,
        total_loc=12, average_cc=complexity, max_cc=complexity,
        average_mi=80.0, quality_gate_passed=False,
        issues=issues or [],
        method_metrics=[MethodMetric("src/main.py", "Module", "existing", 1, 12, 12,
                                     0, 1, complexity, complexity, 80.0)],
    )


def issue(path="src/main.py", entity="existing", severity="HIGH"):
    return CodeIssue("AST-123", "AST-Smell", "CODE_SMELL", "Long Method",
                     severity, path, 1, 12, entity, "Example issue")


class TestIncrementalQualityGate(unittest.TestCase):
    def setUp(self):
        self.base = make_report([issue()]).to_dict()

    def test_preexisting_finding_and_complexity_pass_without_regressions(self):
        head = make_report([issue("src\\main.py")])
        apply_incremental_quality_gate(head, self.base, "base-sha", max_cc=10)
        self.assertTrue(head.quality_gate_passed)
        self.assertFalse(head.pr_gate["full_repository_quality_gate_passed"])
        self.assertEqual(head.pr_gate["new_high_or_critical"], 0)
        self.assertEqual(head.pr_gate["complexity_regressions"], 0)
        self.assertIn("pr_gate", head.to_dict())

    def test_new_high_severity_fails(self):
        head = make_report([issue(), issue("src/new.py", "new_function")])
        apply_incremental_quality_gate(head, self.base, "base-sha", max_cc=10)
        self.assertFalse(head.quality_gate_passed)
        self.assertEqual(head.pr_gate["new_high_or_critical"], 1)

    def test_worsened_complexity_over_threshold_fails(self):
        head = make_report([issue()], complexity=13)
        apply_incremental_quality_gate(head, self.base, "base-sha", max_cc=10)
        self.assertFalse(head.quality_gate_passed)
        self.assertEqual(head.pr_gate["complexity_regressions"], 1)

    def test_new_complex_method_fails(self):
        head = make_report([issue()])
        head.method_metrics.append(MethodMetric(
            "src/new.py", "Module", "new_method", 1, 12, 12, 0, 1, 11, 11, 80.0
        ))
        apply_incremental_quality_gate(head, self.base, "base-sha", max_cc=10)
        self.assertFalse(head.quality_gate_passed)

    def test_invalid_baseline_fails_closed(self):
        baseline = make_report().to_dict()
        baseline["files_scanned"] = 0
        head = make_report([issue()])
        apply_incremental_quality_gate(head, baseline, "base-sha", max_cc=10)
        self.assertFalse(head.quality_gate_passed)
        self.assertFalse(head.pr_gate["baseline_valid"])


if __name__ == "__main__":
    unittest.main()
