# SpotAI-Review: Static Code Analysis & AI Code Review Tool

**Course:** Software Engineering — **Group 4**  
**Instructor:** Dr. Nguyen Thanh Hai  
**Team Members:**
- **Duong Le Thuong** (`DTC235340030`) — Core Static Analysis Engine, SpotBugs Bytecode XML Adapter, AST Metrics & Code Smell Rules
- **Duong Quoc Toan** (`DTC235210055`) — Configurable Token/AST Clone Detector, LLM Refactoring Engine, GitHub Actions CI/CD Bot & SARIF/HTML Dashboard

## 1. Overview & Architecture
`SpotAI-Review` is a hybrid static code analysis and automated pull request review system that integrates **SpotBugs bytecode bug detection**, **Multi-Smell AST & Cyclomatic Complexity analysis**, **Type-1/2/3 Clone Detection**, and **LLM-powered Refactoring Suggestions** into a unified CLI and GitHub Actions workflow.

## 2. Quick Start (CLI)
```bash
# Run Milestone 1 (Week 4-6: SpotBugs XML + AST Code Smells & Cyclomatic Complexity)
python3 spotai_cli.py --repo sample_repos/repo1_ecommerce_java --output-dir reports/m1 --milestone 1

# Run Full Pipeline (Milestone 4: SpotBugs + AST + Clone Detector + AI Refactoring + HTML/SARIF)
python3 spotai_cli.py --repo sample_repos/repo1_ecommerce_java --output-dir reports/repo1 --clone-threshold 0.80 --milestone 4

# Run Benchmark Evaluation on both Sample Repositories
python3 evaluate_benchmarks.py

# Run Unit & Integration Tests
python3 -m unittest discover -s tests
```
