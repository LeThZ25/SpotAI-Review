"""
Module 6: Multi-Format Report Exporter (SARIF v2.1.0, Interactive HTML Dashboard, Markdown, JSON)
Owner: Duong Le Thuong & Duong Quoc Toan
"""
import html
import json
import os
from .models import AnalysisReport


class ReportExporter:
    @staticmethod
    def save_json(report: AnalysisReport, path: str):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2)

    @staticmethod
    def save_sarif(report: AnalysisReport, path: str):
        """Exports SARIF v2.1.0 compatible with GitHub Security Code Scanning tab."""
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        results = []
        for issue in report.issues:
            level = "error" if issue.severity == "HIGH" else ("warning" if issue.severity == "MEDIUM" else "note")
            results.append({
                "ruleId": issue.smell_or_bug_type.replace(" ", "_").upper(),
                "level": level,
                "message": {
                    "text": f"{issue.message} | AI Suggestion: {issue.ai_explanation or ''}"
                },
                "locations": [{
                    "physicalLocation": {
                        "artifactLocation": {"uri": issue.file_path},
                        "region": {"startLine": issue.start_line, "endLine": issue.end_line},
                    }
                }],
            })

        sarif_doc = {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [{
                "tool": {
                    "driver": {
                        "name": "SpotAI-Review (Group 4)",
                        "version": "1.0.0",
                        "informationUri": "https://github.com/group4-se/spotai-review",
                    }
                },
                "results": results,
            }],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sarif_doc, f, indent=2)

    @staticmethod
    def save_html_dashboard(report: AnalysisReport, path: str):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        rows_html = []
        for issue in report.issues:
            badge_color = "#dc2626" if issue.severity == "HIGH" else ("#d97706" if issue.severity == "MEDIUM" else "#2563eb")
            rows_html.append(f"""
            <tr>
              <td><code>{html.escape(issue.issue_id)}</code></td>
              <td><span class="badge" style="background:{badge_color}">{html.escape(issue.severity)}</span></td>
              <td><strong>{html.escape(issue.source_engine)}</strong></td>
              <td>{html.escape(issue.smell_or_bug_type)}</td>
              <td><code>{html.escape(issue.file_path)}:{issue.start_line}-{issue.end_line}</code><br/><small>{html.escape(issue.entity_name)}</small></td>
              <td>
                <p style="margin:0 0 6px 0;">{html.escape(issue.message)}</p>
                <details>
                  <summary style="cursor:pointer;color:#1d4ed8;font-weight:600;">View AI Refactoring & Limitations</summary>
                  <div style="margin-top:8px;padding:10px;background:#f8fafc;border-left:3px solid #1d4ed8;">
                    <p><strong>Rationale:</strong> {html.escape(issue.ai_explanation or '')}</p>
                    <pre style="background:#0f172a;color:#f8fafc;padding:10px;border-radius:6px;overflow-x:auto;"><code>{html.escape(issue.ai_refactored_code or '')}</code></pre>
                    <p style="color:#475569;font-size:0.9em;margin-bottom:0;"><strong>Stated Limitations:</strong> {html.escape(issue.ai_limitations or '')}</p>
                  </div>
                </details>
              </td>
            </tr>
            """)

        gate_text = "PASSED" if report.quality_gate_passed else "FAILED"
        gate_bg = "#16a34a" if report.quality_gate_passed else "#dc2626"
        html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>SpotAI-Review Dashboard — {html.escape(report.repository_name)}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; background: #f1f5f9; color: #0f172a; }}
    header {{ background: #1e293b; color: #fff; padding: 20px 32px; display: flex; justify-content: space-between; align-items: center; }}
    .container {{ max-width: 1280px; margin: 24px auto; padding: 0 24px; }}
    .cards {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 16px; margin-bottom: 24px; }}
    .card {{ background: #fff; padding: 18px; border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
    .card h4 {{ margin: 0 0 8px 0; font-size: 0.85rem; color: #64748b; text-transform: uppercase; }}
    .card .val {{ font-size: 1.65rem; font-weight: 700; color: #0f172a; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 10px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
    th {{ background: #1e293b; color: #fff; text-align: left; padding: 12px 14px; font-size: 0.88rem; }}
    td {{ padding: 12px 14px; border-bottom: 1px solid #e2e8f0; vertical-align: top; font-size: 0.9rem; }}
    .badge {{ color: #fff; padding: 3px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 700; }}
  </style>
</head>
<body>
  <header>
    <div>
      <h2 style="margin:0;">SpotAI-Review: Hybrid Static Code Analysis & AI Review</h2>
      <small>Group 4: Duong Le Thuong (DTC235340030) & Duong Quoc Toan (DTC235210055) | Target: {html.escape(report.repository_name)}</small>
    </div>
    <div>
      <span class="badge" style="background:{gate_bg};font-size:0.95rem;padding:8px 14px;">Quality Gate: {gate_text}</span>
    </div>
  </header>
  <div class="container">
    <div class="cards">
      <div class="card"><h4>Files Scanned</h4><div class="val">{report.files_scanned}</div></div>
      <div class="card"><h4>Total Findings</h4><div class="val">{len(report.issues)}</div></div>
      <div class="card"><h4>SpotBugs / AST / Clone</h4><div class="val">{report.summary_by_engine.get('SpotBugs',0)} / {report.summary_by_engine.get('AST-Smell',0)} / {report.summary_by_engine.get('Clone-Detector',0)}</div></div>
      <div class="card"><h4>Avg / Max CC</h4><div class="val">{report.average_cc:.1f} / {report.max_cc}</div></div>
      <div class="card"><h4>Maintainability (MI)</h4><div class="val">{report.average_mi:.1f}</div></div>
    </div>
    <table>
      <thead>
        <tr>
          <th>ID</th>
          <th>Severity</th>
          <th>Engine</th>
          <th>Bug / Code Smell</th>
          <th>Location</th>
          <th>Analysis & AI Refactoring Suggestion</th>
        </tr>
      </thead>
      <tbody>
        {''.join(rows_html)}
      </tbody>
    </table>
  </div>
</body>
</html>"""
        with open(path, "w", encoding="utf-8") as f:
            f.write(html_doc)
