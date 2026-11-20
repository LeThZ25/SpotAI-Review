"""
Module 6: Multi-Format Report Exporter (SARIF v2.1.0, Interactive HTML Dashboard, Markdown, JSON)
Authors: Duong Le Thuong, Duong Quoc Toan & Nguyen Thanh Trung
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
            level = "error" if issue.severity in {"HIGH", "CRITICAL"} else ("warning" if issue.severity == "MEDIUM" else "note")
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
                        "name": "SpotAI-Review",
                        "version": "1.0.0",
                        "informationUri": "https://github.com/LeThZ25/SpotAI-Review",
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
            badge_color = "#dc2626" if issue.severity in {"HIGH", "CRITICAL"} else ("#d97706" if issue.severity == "MEDIUM" else "#2563eb")
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
                  <summary>View AI Refactoring & Limitations</summary>
                  <div class="ai-details">
                    <p><strong>Rationale:</strong> {html.escape(issue.ai_explanation or '')}</p>
                    <p><strong>Provider:</strong> {html.escape(issue.ai_provider or 'Unavailable')}</p>
                    <pre><code>{html.escape(issue.ai_refactored_code or '')}</code></pre>
                    <p class="ai-limitations"><strong>Stated Limitations:</strong> {html.escape(issue.ai_limitations or '')}</p>
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
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>SpotAI-Review Dashboard — {html.escape(report.repository_name)}</title>
  <style>
    :root {{ color-scheme: dark; --bg: #090f1d; --surface: #111d2f; --line: #2c3d55; --text: #f6f9ff; --muted: #b1c1d7; --accent: #67d6f6; }}
    * {{ box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; background: radial-gradient(ellipse at top left, #152f4a, var(--bg) 58%); color: var(--text); line-height: 1.6; }}
    header {{ background: #0b1626; color: #fff; padding: 22px clamp(16px, 3vw, 36px); display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 18px; border-bottom: 1px solid var(--line); }}
    header h2 {{ font-size: clamp(1.15rem, 1rem + 1vw, 1.65rem); }}
    header small {{ color: var(--muted); overflow-wrap: anywhere; }}
    .container {{ max-width: 1280px; margin: 28px auto; padding: 0 clamp(12px, 3vw, 28px); }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 200px), 1fr)); gap: 14px; margin-bottom: 24px; }}
    .card {{ background: var(--surface); padding: 18px; border-radius: 12px; border: 1px solid var(--line); min-width: 0; }}
    .card h4 {{ margin: 0 0 8px 0; font-size: 0.83rem; color: var(--muted); text-transform: uppercase; }}
    .card .val {{ font-size: 1.55rem; font-weight: 700; color: var(--text); overflow-wrap: anywhere; }}
    .table-scroll {{ overflow-x: auto; border-radius: 12px; border: 1px solid var(--line); }}
    table {{ width: 100%; min-width: 850px; border-collapse: collapse; background: var(--surface); }}
    th {{ background: #1c3049; color: #fff; text-align: left; padding: 12px 14px; font-size: 0.85rem; }}
    td {{ padding: 12px 14px; border-bottom: 1px solid var(--line); vertical-align: top; font-size: 0.88rem; overflow-wrap: anywhere; }}
    td code {{ overflow-wrap: anywhere; }}
    td pre {{ white-space: pre-wrap; overflow-wrap: anywhere; max-width: 52ch; }}
    td small {{ color: var(--muted); }}
    details summary {{ cursor: pointer; color: var(--accent); font-weight: 600; }}
    .ai-details {{ margin-top: 8px; padding: 12px; background: #0b1626; border-left: 3px solid var(--accent); border-radius: 6px; }}
    .ai-details pre {{ background: #07101e; color: var(--text); padding: 10px; border-radius: 6px; overflow-x: auto; }}
    .ai-limitations {{ color: var(--muted); font-size: .9em; margin-bottom: 0; }}
    .badge {{ color: #fff; padding: 3px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 700; }}
    :focus-visible {{ outline: 3px solid var(--accent); outline-offset: 3px; }}
    @media (max-width: 600px) {{ .cards {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} header {{ align-items: flex-start; }} }}
  </style>
</head>
<body>
  <header>
    <div>
      <h2 style="margin:0;">SpotAI-Review: Hybrid Static Code Analysis & AI Review</h2>
      <small>Target: {html.escape(report.repository_name)}</small>
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
    <div class="table-scroll" role="region" aria-label="Danh sách vấn đề phân tích" tabindex="0">
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
        {''.join(rows_html) or '<tr><td colspan="6">No code issues detected.</td></tr>'}
      </tbody>
    </table>
    </div>
  </div>
</body>
</html>"""
        with open(path, "w", encoding="utf-8") as f:
            f.write(html_doc)
