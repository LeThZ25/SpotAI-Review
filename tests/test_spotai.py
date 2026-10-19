import os
import sys
import json
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from spotai.pipeline import SpotAIPipeline
from spotai.clone_detector import CloneDetector
from spotai.reporter import ReportExporter


class TestSpotAIReview(unittest.TestCase):
    def setUp(self):
        self.base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.repo1 = os.path.join(self.base_dir, "sample_repos", "repo1_ecommerce_java")
        self.repo2 = os.path.join(self.base_dir, "sample_repos", "repo2_payment_gateway")

    def test_milestone1_spotbugs_and_ast_smells(self):
        pipeline = SpotAIPipeline(milestone=1)
        report = pipeline.analyze(self.repo1)
        self.assertGreaterEqual(report.files_scanned, 2)
        self.assertIn("SpotBugs", report.summary_by_engine)
        self.assertIn("AST-Smell", report.summary_by_engine)
        self.assertNotIn("Clone-Detector", report.summary_by_engine)

    def test_milestone4_full_pipeline_repo1(self):
        pipeline = SpotAIPipeline(clone_threshold=0.80, min_clone_lines=7, milestone=4)
        report = pipeline.analyze(self.repo1)
        self.assertGreaterEqual(len(report.issues), 7)
        self.assertIn("Clone-Detector", report.summary_by_engine)
        # Verify AI refactoring fields are populated with reasons and stated limitations
        for issue in report.issues:
            self.assertIsNotNone(issue.ai_explanation)
            self.assertIsNotNone(issue.ai_refactored_code)
            self.assertIsNotNone(issue.ai_limitations)
            self.assertIn("Limitation", issue.ai_limitations)

    def test_milestone4_full_pipeline_repo2(self):
        pipeline = SpotAIPipeline(clone_threshold=0.80, min_clone_lines=7, milestone=4)
        report = pipeline.analyze(self.repo2)
        self.assertGreaterEqual(len(report.issues), 5)
        self.assertIn("Duplicated Code", report.summary_by_type)

    def test_configurable_clone_threshold(self):
        strict_detector = CloneDetector(similarity_threshold=0.99, min_lines=7)
        relaxed_detector = CloneDetector(similarity_threshold=0.75, min_lines=7)
        strict_clones = strict_detector.detect_clones(self.repo1)
        relaxed_clones = relaxed_detector.detect_clones(self.repo1)
        self.assertGreaterEqual(len(relaxed_clones), len(strict_clones))


if __name__ == "__main__":
    unittest.main()
