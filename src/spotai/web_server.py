"""
Web Server & REST API for SpotAI-Review
Provides high-performance REST APIs and Unified Web UI for:
1. Repository Review (Drag & Drop files/ZIP, Local directory, or remote GitHub URL with Shallow Clone)
2. Live Code Playground (Instant snippet analysis and AI refactoring for Java & Python)
3. Interactive HTML Dashboard & Diagnostics
Serves both standalone browser access and VS Code Extension Webview.
"""
import os
import sys
import shutil
import zipfile
import uuid
import re
from pathlib import Path
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, Body, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Ensure src path is available
src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from spotai.pipeline import SpotAIPipeline
from spotai.repo_resolver import RepoResolver, RepoResolverError
from spotai.snippet_analyzer import SnippetAnalyzer
from spotai.reporter import ReportExporter
from spotai.ai_refactor import AIRefactoringEngine
from spotai.web_security import (
    PROJECT_ROOT, MAX_UPLOAD_BYTES, MAX_ARCHIVE_ENTRIES, allowed_local_repository,
    count_upload, extract_zip_safely, is_within, save_upload, validate_analysis_options, validate_github_https,
    validate_report_id,
)

app = FastAPI(
    title="SpotAI-Review Engine API",
    description="REST API for Static Code Analysis & AI Code Review (SpotBugs + AST + Clone + LLM)",
    version="1.0.0"
)

# Local browser clients are same-origin. Additional origins are opt-in.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in os.environ.get("SPOTAI_CORS_ORIGINS", "").split(",") if x.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

snippet_analyzer = SnippetAnalyzer()


class AnalyzeRepoRequest(BaseModel):
    repo: str
    milestone: int = 4
    clone_threshold: float = 0.80
    min_clone_lines: int = 7
    max_cc: int = 10
    cleanup_temp: bool = True


class AnalyzeSnippetRequest(BaseModel):
    code: str
    language: str  # "java" or "python"


@app.get("/api/health")
def health_check():
    ai_engine = AIRefactoringEngine()
    return {
        "status": "healthy",
        "version": "1.0.0",
        "active_ai_provider": ai_engine.active_provider_label,
        "supported_languages": ["java", "python"],
        "engines": ["SpotBugs Bytecode", "AST Code Smells", "Clone Detector", "AI Refactoring Engine"]
    }


@app.post("/api/analyze-snippet")
def analyze_snippet(req: AnalyzeSnippetRequest):
    """Real-time analysis of code snippets for the Live Code Playground."""
    if len(req.code.encode("utf-8")) > 1024 * 1024:
        raise HTTPException(status_code=413, detail="Snippet exceeds 1 MB.")
    result = snippet_analyzer.analyze_snippet(req.code, req.language)
    return result


@app.post("/api/analyze-repo")
def analyze_repo(req: AnalyzeRepoRequest):
    """
    Analyzes local directory or clones remote GitHub repository with shallow clone.
    Validates presence of Java and Python files with user-friendly warnings.
    """
    repo_input = req.repo.strip()
    if not repo_input:
        raise HTTPException(status_code=400, detail="Repository path or URL cannot be empty.")

    validate_analysis_options(req.milestone, req.clone_threshold, req.min_clone_lines, req.max_cc)
    if RepoResolver.is_git_url(repo_input):
        if not validate_github_https(repo_input):
            raise HTTPException(status_code=400, detail="Web accepts only HTTPS GitHub repository URLs.")
    elif not allowed_local_repository(repo_input):
        raise HTTPException(status_code=403, detail="Repository is outside allowed roots. Configure SPOTAI_ALLOWED_ROOTS.")

    resolver = RepoResolver(temp_base_dir=str(PROJECT_ROOT / "temp_repos"),
                            clone_timeout=45, restrict_redirects=True)
    try:
        repo_dir, is_temp, repo_name = resolver.resolve(repo_input)
    except RepoResolverError as err:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(err)}
        )

    # Pre-scan verification for Java and Python files
    java_files = []
    py_files = []
    for root, dirs, files in os.walk(repo_dir):
        dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", "temp_repos", "node_modules", "target", "build", ".venv"}
                   and is_within(os.path.join(root, d), repo_dir)]
        for f in files:
            if not is_within(os.path.join(root, f), repo_dir):
                continue
            if f.endswith(".java"):
                java_files.append(os.path.join(root, f))
            elif f.endswith(".py"):
                py_files.append(os.path.join(root, f))

    total_supported_files = len(java_files) + len(py_files)
    if total_supported_files == 0:
        if is_temp and req.cleanup_temp:
            resolver.cleanup(repo_dir)
        return {
            "status": "no_supported_files",
            "message": (
                f"No Java (*.java) or Python (*.py) source files were found in '{repo_name}'. "
                "SpotAI-Review specializes in Java and Python. Please verify repository contents."
            ),
            "repository_name": repo_name,
            "files_scanned": 0,
            "report": None
        }

    try:
        pipeline = SpotAIPipeline(
            clone_threshold=req.clone_threshold,
            min_clone_lines=req.min_clone_lines,
            max_cc=req.max_cc,
            milestone=req.milestone,
        )
        report = pipeline.analyze(repo_dir, repo_name=repo_name)

        safe_name = re.sub(r"[^A-Za-z0-9_-]", "_", repo_name)[:100] or "repository"
        out_dir = str(PROJECT_ROOT / "reports" / "web_reports" / safe_name)
        os.makedirs(out_dir, exist_ok=True)

        ReportExporter.save_json(report, os.path.join(out_dir, "analysis_report.json"))
        ReportExporter.save_sarif(report, os.path.join(out_dir, "analysis_report.sarif"))
        ReportExporter.save_html_dashboard(report, os.path.join(out_dir, "dashboard.html"))

        return {
            "status": "success",
            "repository_name": repo_name,
            "is_temporary": is_temp,
            "detected_files": {
                "java": len(java_files),
                "python": len(py_files),
                "total": total_supported_files
            },
            "report": report.to_dict(),
            "dashboard_url": f"/dashboard/{safe_name}"
        }

    finally:
        if is_temp and req.cleanup_temp:
            resolver.cleanup(repo_dir)


@app.post("/api/upload-and-analyze")
async def upload_and_analyze(
    files: List[UploadFile] = File(...),
    milestone: int = Form(4),
    clone_threshold: float = Form(0.80),
    min_clone_lines: int = Form(7),
    max_cc: int = Form(10),
):
    """
    Accepts direct upload or drag & drop of .java, .py, or .zip files.
    Extracts archives, saves files into a temporary isolated workspace, and runs the analysis.
    """
    upload_id = f"upload_{uuid.uuid4().hex[:8]}"
    temp_dir = str(PROJECT_ROOT / "temp_repos" / upload_id)
    os.makedirs(temp_dir, exist_ok=True)

    try:
        validate_analysis_options(milestone, clone_threshold, min_clone_lines, max_cc)
        if len(files) > MAX_ARCHIVE_ENTRIES:
            raise HTTPException(status_code=413, detail="Upload exceeds 1,000 files.")
        remaining = MAX_UPLOAD_BYTES
        archive_entries = 0
        expanded_bytes = 0
        extracted_names = set()
        for file in files:
            filename = file.filename or "unknown"
            lower_name = filename.lower()
            # Reject path components supplied by the client. Windows paths also use backslashes.
            if (not filename or filename in (".", "..") or "/" in filename
                    or "\\" in filename or ":" in filename):
                raise HTTPException(status_code=400, detail="Upload filename contains a path.")
            if lower_name.endswith(".zip"):
                zip_path = Path(temp_dir) / f"{uuid.uuid4().hex}.zip"
                remaining -= await save_upload(file, zip_path, remaining)
                archive_entries, expanded_bytes = extract_zip_safely(
                    zip_path, Path(temp_dir), archive_entries, expanded_bytes, extracted_names,
                )
                zip_path.unlink()
            elif lower_name.endswith(".java") or lower_name.endswith(".py"):
                file_dest = Path(temp_dir) / filename
                if file_dest.exists() or str(file_dest).casefold() in extracted_names:
                    raise HTTPException(status_code=400, detail="Duplicate upload filename.")
                extracted_names.add(str(file_dest).casefold())
                remaining -= await save_upload(file, file_dest, remaining)
            else:
                # Preserve the existing no_supported_files response for unsupported uploads.
                remaining -= await count_upload(file, remaining)
                continue

        # Scan for Java and Python files
        java_files = []
        py_files = []
        for root, dirs, f_list in os.walk(temp_dir):
            dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", "node_modules", "target", "build", ".venv"}
                       and is_within(os.path.join(root, d), temp_dir)]
            for f in f_list:
                if not is_within(os.path.join(root, f), temp_dir):
                    continue
                if f.endswith(".java"):
                    java_files.append(os.path.join(root, f))
                elif f.endswith(".py"):
                    py_files.append(os.path.join(root, f))

        total_supported = len(java_files) + len(py_files)
        if total_supported == 0:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return {
                "status": "no_supported_files",
                "message": (
                    "No Java (*.java) or Python (*.py) source files were found in the uploaded file(s). "
                    "SpotAI-Review specializes in Java and Python. Please upload .java, .py, or a .zip archive containing them."
                ),
                "repository_name": upload_id,
                "files_scanned": 0,
                "report": None
            }

        pipeline = SpotAIPipeline(
            clone_threshold=clone_threshold,
            min_clone_lines=min_clone_lines,
            max_cc=max_cc,
            milestone=milestone,
        )
        report = pipeline.analyze(temp_dir, repo_name=upload_id)

        out_dir = str(PROJECT_ROOT / "reports" / "web_reports" / upload_id)
        os.makedirs(out_dir, exist_ok=True)

        ReportExporter.save_json(report, os.path.join(out_dir, "analysis_report.json"))
        ReportExporter.save_sarif(report, os.path.join(out_dir, "analysis_report.sarif"))
        ReportExporter.save_html_dashboard(report, os.path.join(out_dir, "dashboard.html"))

        return {
            "status": "success",
            "repository_name": upload_id,
            "is_temporary": True,
            "detected_files": {
                "java": len(java_files),
                "python": len(py_files),
                "total": total_supported
            },
            "report": report.to_dict(),
            "dashboard_url": f"/dashboard/{upload_id}"
        }

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.get("/dashboard/{repo_name}", response_class=HTMLResponse)
def get_dashboard(repo_name: str):
    """Serves the generated interactive HTML dashboard for a specific repository."""
    if not validate_report_id(repo_name):
        raise HTTPException(status_code=404, detail="Invalid dashboard name.")
    dashboard_path = str(PROJECT_ROOT / "reports" / "web_reports" / repo_name / "dashboard.html")
    report_root = str(PROJECT_ROOT / "reports" / "web_reports")
    if not is_within(dashboard_path, report_root):
        raise HTTPException(status_code=404, detail="Invalid dashboard path.")
    if not os.path.exists(dashboard_path):
        # Fallback to local demo if exists
        alt_path = str(PROJECT_ROOT / "reports" / repo_name / "dashboard.html")
        if is_within(alt_path, PROJECT_ROOT / "reports") and os.path.exists(alt_path):
            dashboard_path = alt_path
        else:
            raise HTTPException(status_code=404, detail=f"Dashboard for repository '{repo_name}' not found.")

    with open(dashboard_path, "r", encoding="utf-8") as f:
        return f.read()


@app.get("/reports/{repo_name}/{format_name}")
def download_report(repo_name: str, format_name: str):
    """Download reports produced by either Web workflow."""
    formats = {
        "json": ("analysis_report.json", "application/json"),
        "sarif": ("analysis_report.sarif", "application/json"),
        "html": ("dashboard.html", "text/html"),
    }
    if not validate_report_id(repo_name) or format_name not in formats:
        raise HTTPException(status_code=404, detail="Unknown report format or repository.")
    filename, content_type = formats[format_name]
    root = PROJECT_ROOT / "reports" / "web_reports"
    target = root / repo_name / filename
    if not is_within(target, root) or not target.is_file():
        raise HTTPException(status_code=404, detail="Report not found.")
    return FileResponse(str(target), media_type=content_type, filename=filename)


@app.get("/", response_class=HTMLResponse)
def serve_index():
    """Serves the Unified SpotAI-Review Web Application (Repository Review + Live Playground)."""
    return get_unified_html()


def get_unified_html() -> str:
    return """<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>SpotAI-Review • Code Quality & AI Review Platform</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f3f6fb;
      --card-bg: #ffffff;
      --card-border: #dce5f1;
      --accent: #4c55e6;
      --accent-hover: #363fc5;
      --text: #15243b;
      --text-muted: #5e7087;
      --success: #078a6c;
      --warning: #aa6705;
      --danger: #cf385a;
      --code-bg: #0e1b2c;
      --shadow: 0 16px 48px rgba(21, 45, 79, .065);
    }
    *, *::before, *::after { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body {
      min-width: 0; min-height: 100vh; margin: 0; color: var(--text);
      background: radial-gradient(circle at 88% 3%, #e7e9ff 0, transparent 28%), var(--bg);
      font: 400 15px/1.65 "Segoe UI Variable", "Segoe UI", system-ui, sans-serif;
      -webkit-font-smoothing: antialiased;
    }
    button, input, select, textarea { font: inherit; }
    button, a { -webkit-tap-highlight-color: transparent; }
    button { cursor: pointer; }
    a { color: inherit; }
    :where(button, input, select, textarea, a, .drop-trigger):focus-visible {
      outline: 3px solid #8593ff; outline-offset: 3px;
    }
    .visually-hidden { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
    header {
      position: sticky; top: 0; z-index: 20; display: flex; align-items: center;
      justify-content: space-between; flex-wrap: wrap; gap: 16px; padding: 13px clamp(18px, 4vw, 55px);
      background: #101e33; color: #f3f7ff; border-bottom: 1px solid #2b3a54;
      box-shadow: 0 12px 28px rgba(8, 23, 43, .08);
    }
    .brand { display: flex; align-items: center; gap: 12px; min-width: 0; }
    .brand-logo {
      display: grid; place-items: center; flex: 0 0 41px; height: 41px;
      background: linear-gradient(140deg, #8d97ff, #4bd1c5); border-radius: 13px;
      color: #0f2032; font-weight: 900; font-size: 22px; box-shadow: 0 5px 20px #35bdb82b;
    }
    .brand-text h1 { margin: 0; font-size: 17px; letter-spacing: -.035em; line-height: 1.3; }
    .brand-text p { margin: 1px 0 0; color: #a9bed7; font-size: 11px; letter-spacing: .025em; }
    .nav-tabs { display: flex; flex-wrap: wrap; align-items: center; gap: 5px; padding: 5px; background: #1c3049; border: 1px solid #33465c; border-radius: 13px; }
    .nav-tab { min-height: 39px; border: 0; border-radius: 9px; padding: 9px 13px; background: transparent; color: #c3d3e7; font-size: 12px; font-weight: 650; transition: color .2s, background .2s, transform .2s; }
    .nav-tab:hover { background: #2c415e; color: #fff; }
    .nav-tab.active { background: #fff; color: #18233e; box-shadow: 0 3px 12px #0002; }
    .container { max-width: 1370px; padding: 0 clamp(15px, 3vw, 36px) 56px; margin: 0 auto; }
    .hero {
      position: relative; display: flex; justify-content: space-between; align-items: center;
      overflow: hidden; gap: 28px; margin: 27px 0 23px; padding: clamp(27px, 5vw, 48px);
      background: linear-gradient(110deg, #172641, #22375c 58%, #254b60);
      color: #fff; border-radius: 25px; box-shadow: 0 21px 46px #192b4930;
      isolation: isolate;
    }
    .hero::before { content: ''; position: absolute; z-index: -1; width: 400px; aspect-ratio: 1; right: -110px; top: -180px; border-radius: 50%; border: 70px solid #79ded21c; box-shadow: 0 0 0 70px #8c93fa0a; }
    .hero::after { content: ''; position: absolute; z-index: -1; width: 300px; aspect-ratio: 1; right: 14%; bottom: -245px; border-radius: 50%; background: #4c55e62b; filter: blur(32px); }
    .eyebrow { display: inline-block; margin: 0 0 12px; color: #91e7df; letter-spacing: .18em; font-size: 10px; font-weight: 800; text-transform: uppercase; }
    .hero h2 { max-width: 710px; margin: 0; font-size: clamp(27px, 3.5vw, 47px); letter-spacing: -.045em; line-height: 1.15; font-weight: 750; }
    .hero h2 em { font-style: normal; color: #9dece2; }
    .hero p { max-width: 680px; margin: 16px 0 0; color: #c0d2e5; font-size: 13px; }
    .hero-tags { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 21px; }
    .hero-tags span { padding: 5px 11px; font-size: 11px; font-weight: 600; color: #d9eafa; border: 1px solid #8aa4bb55; border-radius: 30px; background: #ffffff0d; }
    .hero-indicator { flex: 0 0 auto; display: flex; align-items: center; gap: 9px; padding: 11px 14px; background: #081b2880; border: 1px solid #85e4d433; border-radius: 12px; font-size: 12px; color: #d8efe9; }
    .status-dot { display: block; width: 8px; height: 8px; border-radius: 50%; background: #77ead4; box-shadow: 0 0 0 5px #7be8c722; }
    .tab-content { display: none; }
    .tab-content.active { display: block; animation: enter .35s cubic-bezier(.2,.7,.2,1) both; }
    .workspace-grid { display: grid; grid-template-columns: minmax(0, 1.75fr) minmax(245px, .7fr); align-items: stretch; gap: 20px; margin-bottom: 20px; }
    .card, .sidebar-card {
      min-width: 0; margin-bottom: 20px; padding: clamp(20px, 2.3vw, 30px);
      background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 20px;
      box-shadow: var(--shadow);
    }
    .workspace-grid .card { margin-bottom: 0; }
    .sidebar-card { position: relative; overflow: hidden; background: #eaf1fb; border-color: #d8e4f2; }
    .sidebar-card::before { content: ''; position: absolute; height: 5px; top: 0; left: 0; right: 0; background: linear-gradient(90deg, #4c55e6, #38bcad); }
    .sidebar-heading { margin: 7px 0 17px; font-size: 17px; font-weight: 750; letter-spacing: -.03em; }
    .guide-step { display: grid; grid-template-columns: 33px minmax(0,1fr); gap: 10px; padding: 15px 0; border-top: 1px solid #cbd9e9; }
    .guide-number { display: grid; place-items: center; width: 31px; height: 31px; background: #fff; border: 1px solid #cdd9f1; border-radius: 10px; color: #4c55e6; font-size: 12px; font-weight: 800; }
    .guide-step strong { display: block; font-size: 13px; }
    .guide-step p { margin: 3px 0 0; font-size: 12px; color: var(--text-muted); line-height: 1.6; }
    .sidebar-note { margin-top: 14px; padding: 12px; border: 1px solid #bfd9d9; background: #dbf1ed; border-radius: 12px; color: #285a57; font-size: 12px; }
    .card-title { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin: 0 0 9px; color: #172741; font-size: clamp(17px, 1.5vw, 21px); font-weight: 750; line-height: 1.3; letter-spacing: -.03em; }
    .card-desc { max-width: 72ch; margin: 0 0 22px; color: var(--text-muted); font-size: 13px; line-height: 1.7; }
    .mode-pills { display: flex; flex-wrap: wrap; gap: 9px; margin: 0 0 20px; padding-bottom: 17px; border-bottom: 1px solid #e6edf5; }
    .mode-btn, .badge-sample { min-height: 40px; padding: 8px 14px; border: 1px solid #d9e3f0; background: #f7f9fd; color: #50647f; border-radius: 11px; font-size: 12px; font-weight: 650; transition: transform .2s, background .2s, border-color .2s; }
    .mode-btn:hover, .badge-sample:hover { border-color: #919bf0; transform: translateY(-1px); }
    .mode-btn.active-mode { background: #eaeaff; color: #353eb9; border-color: #afb5ff; }
    .drop-zone { border: 2px dashed #a4b2db; border-radius: 15px; background: linear-gradient(125deg, #f7f8ff, #f0f8fb); transition: border-color .2s, background .2s, transform .2s; }
    .drop-zone:hover, .drop-zone.dragover { border-color: #4c55e6; background: #e9ecff; transform: translateY(-2px); }
    .drop-zone:focus-within { outline: 3px solid #a6adff; outline-offset: 2px; }
    .drop-trigger { display: block; padding: clamp(22px, 3vw, 38px) 16px; text-align: center; cursor: pointer; }
    .drop-icon { display: grid; place-items: center; width: 56px; height: 56px; margin: 0 auto 14px; border-radius: 16px; background: #e0e4ff; font-size: 25px; }
    .drop-title { max-width: 520px; margin: 0 auto 5px; font-size: 14px; font-weight: 700; }
    .drop-subtitle { font-size: 12px; color: var(--text-muted); }
    .file-list { display: flex; justify-content: flex-start; flex-wrap: wrap; gap: 9px; margin: 13px 0; }
    .file-chip { display: flex; align-items: center; gap: 8px; max-width: 100%; padding: 5px 11px; border: 1px solid #bdcaf4; background: #eef0ff; color: #3645ac; border-radius: 9px; font-size: 11px; overflow-wrap: anywhere; }
    .file-chip-remove { padding: 4px; color: #6577a1; border: 0; background: transparent; font-size: 17px; }
    .file-chip-remove:hover { color: var(--danger); }
    .input-group { display: flex; flex-wrap: wrap; align-items: center; gap: 11px; margin: 15px 0 0; }
    .input-group input[type="text"] { flex: 1 1 280px; min-width: 0; }
    input[type="text"], select, textarea { max-width: 100%; min-height: 44px; border: 1px solid #cbd8e9; border-radius: 10px; padding: 9px 12px; background: #fff; color: var(--text); transition: border-color .2s, box-shadow .2s; }
    :where(input[type="text"], select, textarea):focus { border-color: #6873fa; box-shadow: 0 0 0 3px #6576f519; outline: 0; }
    .btn { display: inline-flex; align-items: center; justify-content: center; gap: 8px; min-height: 44px; padding: 10px 17px; border: 1px solid transparent; border-radius: 11px; background: #4c55e6; color: #fff; font-size: 12px; font-weight: 750; text-align: center; text-decoration: none; transition: background .2s, transform .2s, box-shadow .2s; }
    .btn:hover:not(:disabled) { background: var(--accent-hover); transform: translateY(-2px); box-shadow: 0 7px 18px #4c55e638; }
    .btn:active:not(:disabled) { transform: translateY(0); }
    .btn:disabled { opacity: .54; cursor: not-allowed; }
    .btn-secondary { background: #f4f7fc; color: #344b70; border-color: #cddbec; }
    .btn-secondary:hover:not(:disabled) { background: #e5eafa; color: #202b6d; }
    .grid-4 { display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 14px; margin-bottom: 20px; }
    .metric-card { min-width: 0; padding: 20px; border: 1px solid #dce5f1; border-radius: 17px; background: #fff; box-shadow: var(--shadow); border-top: 3px solid #8187f1; animation: enter .45s both; }
    .metric-card:nth-child(2) { animation-delay: .04s; border-top-color: #37b7af; }
    .metric-card:nth-child(3) { animation-delay: .08s; border-top-color: #e2ac67; }
    .metric-card:nth-child(4) { animation-delay: .12s; border-top-color: #9598af; }
    .metric-card.good { border-top-color: #23ae88; }
    .metric-card.danger { border-top-color: #ec6d82; }
    .metric-label { font-size: 10px; letter-spacing: .12em; text-transform: uppercase; font-weight: 800; color: #6a7b90; }
    .metric-val { margin: 7px 0 3px; color: #192b47; font-size: clamp(20px, 2.4vw, 29px); font-weight: 800; line-height: 1.3; overflow-wrap: anywhere; letter-spacing: -.04em; }
    .metric-sub { color: var(--text-muted); font-size: 11px; }
    .results-toolbar, .filter-row, .report-links { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
    .results-toolbar { justify-content: space-between; margin-bottom: 23px; gap: 16px; }
    .results-toolbar .card-title { margin: 0; }
    .report-links a { min-height: 37px; }
    .filter-row { padding: 13px 0 23px; border-top: 1px solid #e9eff6; }
    .filter-row label { font-size: 12px; color: var(--text-muted); }
    .filter-row input[type="text"] { flex: 1 1 200px; min-width: 0; }
    .filter-row select { min-width: 130px; }
    .filter-hint, .field-hint { color: var(--text-muted); font-size: 12px; }
    .field-hint { margin: 7px 0 13px; }
    .issue-item { overflow: hidden; margin: 0 0 11px; border: 1px solid #dae5f0; border-radius: 13px; background: #fff; }
    .issue-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; width: 100%; min-height: 54px; padding: 14px; border: none; background: #f7f9fc; color: inherit; text-align: left; font: inherit; transition: background .2s; }
    .issue-header:hover { background: #eef2fb; }
    .issue-header > span:first-child { min-width: 0; flex-wrap: wrap; }
    .issue-header code { overflow-wrap: anywhere; }
    .issue-body { padding: 16px; border-top: 1px solid #dce6ef; color: #3e526a; font-size: 13px; overflow-wrap: anywhere; }
    .badge { display: inline-block; padding: 3px 8px; border-radius: 7px; font-size: 10px; font-weight: 800; text-transform: uppercase; letter-spacing: .04em; }
    .badge-high { background: #ffe8ed; color: #ac294d; border: 1px solid #ffbecd; }
    .badge-medium { background: #fff1df; color: #925906; border: 1px solid #f3d6a9; }
    .badge-low { background: #e8f4ff; color: #2965a7; border: 1px solid #bedaff; }
    .limitations-alert { padding: 11px; margin: 10px 0; border-radius: 9px; border: 1px solid #f0cd85; background: #fff5df; color: #865516; font-size: 12px; }
    .banner-alert, .status-notice { padding: 13px 15px; margin: 12px 0 17px; border-radius: 10px; background: #ffe9ee; color: #943449; border: 1px solid #f5bfd0; font-size: 13px; }
    .status-notice.warning { background: #fff2d8; color: #78530b; border-color: #eed39c; }
    .status-notice:not(.warning):not(.error) { background: #e4f5f0; color: #1c6a57; border-color: #b7e5d7; }
    .playground-split { display: grid; grid-template-columns: minmax(0,1.08fr) minmax(0,.92fr); gap: 22px; }
    .playground-split > div { min-width: 0; }
    .quick-samples { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 0 0 17px; }
    .badge-sample { min-height: 34px; padding: 5px 10px; }
    .code-editor { display: block; width: 100%; height: 400px; min-height: 260px; resize: vertical; padding: 18px; border-radius: 13px; background: #112037; color: #e3eefa; border-color: #324563; font: 13px/1.6 Consolas, "Cascadia Code", monospace; tab-size: 4; }
    .code-editor:focus { border-color: #899aff; box-shadow: 0 0 0 3px #586ff244; }
    .code-editor.dragover { border: 2px dashed #93e7d3; background: #1d3650; }
    .diff-block { margin: 10px 0; padding: 15px; overflow: auto; border-radius: 11px; border: 1px solid #2b4360; background: var(--code-bg); color: #dbe8fb; font: 12px/1.65 Consolas, monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
    .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid #ffffff66; border-top-color: currentColor; border-radius: 50%; animation: spin .8s linear infinite; }
    @keyframes spin { to { transform: rotate(360deg); } }
    @keyframes enter { from { opacity: 0; transform: translateY(13px); } to { opacity: 1; transform: translateY(0); } }
    @media (max-width: 1100px) {
      header { position: static; }
      .workspace-grid { grid-template-columns: minmax(0,1fr); }
      .sidebar-card { display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 0 12px; }
      .sidebar-heading, .sidebar-note { grid-column: 1/-1; }
      .playground-split { grid-template-columns: minmax(0,1fr); }
      .grid-4 { grid-template-columns: repeat(2, minmax(0,1fr)); }
    }
    @media (max-width: 700px) {
      header { padding: 14px; }
      .brand { width: 100%; }
      .nav-tabs { width: 100%; }
      .nav-tab { flex: 1 1 130px; padding: 9px 7px; }
      .hero { margin: 15px 0 18px; padding: 25px 21px; border-radius: 19px; flex-wrap: wrap; }
      .hero-indicator { width: fit-content; }
      .card, .sidebar-card { padding: 19px 16px; margin-bottom: 16px; border-radius: 16px; }
      .workspace-grid { gap: 0; }
      .sidebar-card { display: block; }
      .guide-step { padding: 10px 0; }
      .input-group, .input-group > input, .input-group > select, .input-group > .btn, .mode-btn { width: 100%; }
      .input-group > input[type="text"] { flex-basis: 100%; }
      #repo-milestone, #upload-milestone { width: 100% !important; }
      .drop-trigger { padding: 20px 12px; }
      .metric-card { padding: 14px; }
      .report-links { width: 100%; }
      .report-links a { flex: 1 1 130px; }
      .filter-row > * { flex: 1 1 100%; }
      .filter-row select { width: 100%; }
    }
    @media (max-width: 360px) { .grid-4 { grid-template-columns: 1fr; } .nav-tab { flex: 1 1 100%; } }
    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after { scroll-behavior: auto !important; animation-duration: .01ms !important; animation-delay: 0ms !important; transition-duration: .01ms !important; }
    }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <div class="brand-logo">S</div>
      <div class="brand-text">
        <h1>SpotAI-Review</h1>
        <p>Code quality workspace · Python & Java</p>
      </div>
    </div>
    <div class="nav-tabs" aria-label="Điều hướng chức năng">
      <button class="nav-tab active" id="tab-btn-repo" aria-current="page" onclick="switchTab('repo-tab')">📁 Repository Reviewer</button>
      <button class="nav-tab" id="tab-btn-playground" onclick="switchTab('playground-tab')">⚡ Live Code Playground</button>
      <button class="nav-tab" id="tab-btn-arch" onclick="switchTab('arch-tab')">🧠 Architecture & Metrics</button>
    </div>
  </header>

  <main class="container">
    <section class="hero" aria-label="Giới thiệu SpotAI-Review">
      <div>
        <span class="eyebrow">Code intelligence · Review workspace</span>
        <h2>Phát hiện vấn đề sớm.<br><em>Cải thiện mã nguồn tốt hơn.</em></h2>
        <p>Phân tích Python và Java, khám phá code smell, complexity, đoạn mã trùng lặp và đề xuất refactoring tại một nơi.</p>
        <div class="hero-tags"><span>Python &amp; Java</span><span>Static analysis</span><span>AI suggestions</span><span>JSON · SARIF · HTML</span></div>
      </div>
      <div class="hero-indicator"><span class="status-dot" aria-hidden="true"></span> Sẵn sàng phân tích</div>
    </section>
    <!-- TAB 1: REPOSITORY REVIEWER -->
    <div id="repo-tab" class="tab-content active">
      <div class="workspace-grid">
      <section class="card entry-card">
        <div class="card-title">Phân tích repository</div>
        <div class="card-desc">Tải lên file mã nguồn trực tiếp bằng cách kéo thả, hoặc quét qua đường dẫn thư mục / GitHub URL.</div>
        
        <div class="mode-pills">
          <button id="mode-btn-upload" class="mode-btn active-mode" aria-pressed="true" onclick="switchRepoMode('upload')">📂 Kéo thả File / Thư mục ZIP</button>
          <button id="mode-btn-url" class="mode-btn" aria-pressed="false" onclick="switchRepoMode('url')">🔗 GitHub URL / Thư mục Local</button>
        </div>

        <div id="repo-alert-zone" role="status" aria-live="polite"></div>

        <!-- MODE 1: DRAG & DROP UPLOAD -->
        <div id="mode-upload-container">
          <div id="drop-zone" class="drop-zone">
            <label for="file-upload-input" class="drop-trigger">
              <div class="drop-icon" aria-hidden="true">📁</div>
              <div class="drop-title">Kéo & thả file <code>.java</code>, <code>.py</code> hoặc file <code>.zip</code> dự án vào đây</div>
              <div class="drop-subtitle">Hoặc <u>chọn file từ máy tính</u> (hỗ trợ nhiều file, tổng tối đa 20 MB)</div>
            </label>
            <input type="file" id="file-upload-input" multiple accept=".java,.py,.zip" class="visually-hidden" aria-label="Chọn tệp mã nguồn hoặc ZIP" onchange="handleFileSelect(event)" />
          </div>
          <div id="file-chips" class="file-list" aria-live="polite"></div>
          <div class="input-group" style="justify-content: flex-end; align-items:center;">
            <label for="upload-milestone" style="font-size:0.85rem; color:var(--text-muted); margin-right:4px;">Chế độ Milestone:</label>
            <select id="upload-milestone" style="width: 180px;">
              <option value="4">Milestone 4 (Full Hybrid)</option>
              <option value="3">Milestone 3 (PR Bot)</option>
              <option value="2">Milestone 2 (AI + Clone)</option>
              <option value="1">Milestone 1 (SpotBugs + AST)</option>
            </select>
            <button class="btn" id="upload-btn" onclick="runUploadAnalysis()" disabled>
              <span id="upload-btn-text">Quét các File đã Tải lên</span>
            </button>
          </div>
        </div>

        <!-- MODE 2: URL / LOCAL PATH -->
        <div id="mode-url-container" style="display: none;">
          <div class="input-group">
            <label for="repo-input" class="visually-hidden">Đường dẫn repository hoặc URL GitHub HTTPS</label>
            <input type="text" id="repo-input" placeholder="e.g. sample_repos/repo1_ecommerce_java hoặc https://github.com/bottlepy/bottle" value="sample_repos/repo1_ecommerce_java" required aria-invalid="false" oninput="invalidateRepositoryResults()" />
            <label for="repo-milestone" class="visually-hidden">Chế độ Milestone</label>
            <select id="repo-milestone" style="width: 180px;">
              <option value="4">Milestone 4 (Full Hybrid)</option>
              <option value="3">Milestone 3 (PR Bot)</option>
              <option value="2">Milestone 2 (AI + Clone)</option>
              <option value="1">Milestone 1 (SpotBugs + AST)</option>
            </select>
            <button class="btn" id="repo-btn" onclick="runRepoAnalysis()">
              <span id="repo-btn-text">Run SpotAI Review</span>
            </button>
          </div>
        </div>
      </section>
      <aside class="sidebar-card" aria-label="Các bước phân tích">
        <div class="sidebar-heading">Cách sử dụng</div>
        <div class="guide-step"><span class="guide-number">01</span><div><strong>Chọn nguồn mã</strong><p>Tải file Python, Java, ZIP hoặc nhập đường dẫn repository.</p></div></div>
        <div class="guide-step"><span class="guide-number">02</span><div><strong>Chạy phân tích</strong><p>Chọn milestone phù hợp rồi bắt đầu kiểm tra chất lượng.</p></div></div>
        <div class="guide-step"><span class="guide-number">03</span><div><strong>Xem và xuất kết quả</strong><p>Lọc lỗi theo mức độ, xem gợi ý sửa và tải báo cáo.</p></div></div>
        <div class="sidebar-note">Tệp tải lên hỗ trợ .py, .java, .zip với tổng dung lượng tối đa 20 MB.</div>
      </aside>
      </div>

      <div id="repo-results" style="display: none;">
        <div class="grid-4">
          <div class="metric-card" id="card-qg">
            <div class="metric-label">Quality Gate</div>
            <div class="metric-val" id="res-qg">-</div>
            <div class="metric-sub" id="res-qg-sub">Target: 0 High Issues & CC &le; 10</div>
          </div>
          <div class="metric-card">
            <div class="metric-label">Files & LOC</div>
            <div class="metric-val" id="res-files">-</div>
            <div class="metric-sub" id="res-loc">-</div>
          </div>
          <div class="metric-card">
            <div class="metric-label">Average / Max CC</div>
            <div class="metric-val" id="res-cc">-</div>
            <div class="metric-sub">McCabe Cyclomatic Complexity</div>
          </div>
          <div class="metric-card">
            <div class="metric-label">Maintainability Index</div>
            <div class="metric-val" id="res-mi">-</div>
            <div class="metric-sub">Target: &ge; 65.0 / 100.0</div>
          </div>
        </div>

        <div class="card">
          <div class="results-toolbar">
            <div class="card-title" style="margin-bottom:0;">Vấn đề được phát hiện &amp; đề xuất sửa (<span id="res-issues-count">0</span>)</div>
            <div class="report-links">
              <a id="btn-report-json" download class="btn btn-secondary" style="font-size:0.82rem; padding:6px 14px;">Download JSON</a>
              <a id="btn-report-sarif" download class="btn btn-secondary" style="font-size:0.82rem; padding:6px 14px;">Download SARIF</a>
              <a id="btn-full-dashboard" target="_blank" rel="noopener noreferrer" class="btn btn-secondary" style="font-size:0.82rem; padding: 6px 14px;">Open Full HTML Dashboard ↗</a>
            </div>
          </div>
          <div class="filter-row">
            <label for="issue-filter-severity">Lọc mức độ</label>
            <select id="issue-filter-severity" onchange="filterRepositoryIssues()">
              <option value="all">Tất cả</option>
              <option value="CRITICAL">Critical</option>
              <option value="HIGH">High</option>
              <option value="MEDIUM">Medium</option>
              <option value="LOW">Low</option>
            </select>
            <label for="issue-filter-search">Tìm theo tệp hoặc loại lỗi</label>
            <input type="text" id="issue-filter-search" placeholder="Nhập tên tệp, loại lỗi..." oninput="filterRepositoryIssues()" />
            <span id="issue-filter-count" class="filter-hint" aria-live="polite"></span>
          </div>
          <div id="repo-issues-list"></div>
        </div>
      </div>
    </div>

    <!-- TAB 2: LIVE CODE PLAYGROUND -->
    <div id="playground-tab" class="tab-content">
      <div class="card">
        <div class="card-title">Live Code Playground</div>
        <div class="card-desc">Nhập hoặc <strong>kéo thả trực tiếp file .java / .py vào khung soạn thảo bên dưới</strong>. SpotAI-Review tính toán McCabe CC, Cognitive Complexity, Maintainability Index và sinh bản vá Before/After real-time.</div>
        
        <div class="quick-samples">
          <span style="font-size:0.8rem; color:var(--text-muted); align-self:center;">Quick Test Samples:</span>
          <button class="badge-sample" onclick="loadSample('sql_java')">SQL Injection & Null Check (Java)</button>
          <button class="badge-sample" onclick="loadSample('nested_java')">Deeply Nested Loop & High CC (Java)</button>
          <button class="badge-sample" onclick="loadSample('param_py')">Long Parameter List (Python)</button>
          <button class="badge-sample" onclick="loadSample('clean_py')">Clean Code Example (Python)</button>
        </div>

        <div class="playground-split">
          <div class="editor-wrapper">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
              <label for="snippet-code" style="font-size:0.85rem; font-weight:600;">Input Source Code (Kéo thả file vào đây):</label>
              <label for="snippet-lang" class="visually-hidden">Ngôn ngữ mã nguồn</label>
              <select id="snippet-lang" style="padding: 4px 10px; font-size:0.82rem;" onchange="onLangChange()">
                <option value="java">Java (.java)</option>
                <option value="python">Python (.py)</option>
              </select>
            </div>
            <textarea id="snippet-code" class="code-editor" placeholder="// Paste your Java or Python method here, or drag & drop a .java / .py file..." oninput="invalidateSnippetResults('Mã nguồn đã thay đổi. Nhấn Analyze để phân tích lại.')"></textarea>
            <p class="field-hint">Đổi ngôn ngữ sẽ giữ nguyên nội dung đang nhập. Chọn mã mẫu để thử nhanh.</p>
            <div id="snippet-alert-zone" role="status" aria-live="polite"></div>
            <div style="margin-top: 12px; display:flex; justify-content:flex-end;">
              <button class="btn" id="snippet-btn" onclick="runSnippetAnalysis()">
                <span id="snippet-btn-text">Analyze & Refactor Code</span>
              </button>
            </div>
          </div>

          <div>
            <div style="font-size:0.85rem; font-weight:600; margin-bottom:8px;">Real-Time Review Results:</div>
            <div id="snippet-results-placeholder" role="status" style="min-height: 300px; border: 1px dashed var(--card-border); border-radius: 10px; display: flex; align-items:center; justify-content:center; color:var(--text-muted); font-size:0.88rem; text-align:center; padding:20px;">
              Paste code on the left or drop a source file,<br/>then click "Analyze & Refactor Code" to see real-time metrics and AI refactoring.
            </div>
            <div id="snippet-results" style="display:none;">
              <div class="grid-4" style="grid-template-columns: repeat(2, 1fr); margin-bottom: 16px;">
                <div class="metric-card">
                  <div class="metric-label">Cyclomatic Complexity</div>
                  <div class="metric-val" id="snip-cc">-</div>
                  <div class="metric-sub">McCabe independent paths</div>
                </div>
                <div class="metric-card">
                  <div class="metric-label">Maintainability Index</div>
                  <div class="metric-val" id="snip-mi">-</div>
                  <div class="metric-sub">Score out of 100.0</div>
                </div>
              </div>

              <div class="card" style="padding: 16px; margin-bottom: 16px;">
                <div style="font-size: 0.88rem; font-weight: 700; margin-bottom: 8px;">Detected Smells / Defects (<span id="snip-issues-count">0</span>):</div>
                <div id="snip-issues-list"></div>
              </div>

              <div class="card" style="padding: 16px;">
                <div style="font-size: 0.88rem; font-weight: 700; margin-bottom: 8px;">🤖 AI Refactoring Patch:</div>
                <div id="snip-ai-explanation" style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 8px;"></div>
                <div id="snip-ai-limitations" class="field-hint"></div>
                <pre class="diff-block"><code id="snip-diff">-</code></pre>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- TAB 3: ARCHITECTURE & METRICS -->
    <div id="arch-tab" class="tab-content">
      <div class="card">
        <div class="card-title">Kiến trúc &amp; bộ máy phân tích</div>
        <div class="card-desc">Các bộ máy phân tích và chỉ số chất lượng được sử dụng trong SpotAI-Review.</div>
        
        <div class="grid-4" style="margin-top: 20px;">
          <div class="metric-card">
            <div class="metric-label">Engine 1</div>
            <div class="metric-val" style="font-size:1.2rem;">SpotBugs XML</div>
            <div class="metric-sub">Parses bytecode bug reports (NullPtr, SQLi, Resource Leaks) via native XML parser.</div>
          </div>
          <div class="metric-card">
            <div class="metric-label">Engine 2</div>
            <div class="metric-val" style="font-size:1.2rem;">AST Smells</div>
            <div class="metric-sub">Detects Long Method, God Class, Feature Envy, Long Parameters, Deep Nesting.</div>
          </div>
          <div class="metric-card">
            <div class="metric-label">Engine 3</div>
            <div class="metric-val" style="font-size:1.2rem;">Clone Detector</div>
            <div class="metric-sub">Sliding token-window similarity matching for Type-1, Type-2, and Type-3 clones.</div>
          </div>
          <div class="metric-card">
            <div class="metric-label">Engine 4</div>
            <div class="metric-val" style="font-size:1.2rem;">AI Refactoring</div>
            <div class="metric-sub">Groq (Llama-3.3-70b) & Gemini with deterministic local heuristic fallback.</div>
          </div>
        </div>

        <div class="card" style="margin-top: 16px; background: #f5f8fd;">
          <div class="card-title" style="font-size: 0.95rem;">📊 Software Metric Formulas Implemented</div>
          <ul style="font-size: 0.86rem; color: var(--text-muted); margin-left: 20px; line-height: 1.8;">
            <li><strong>McCabe Cyclomatic Complexity:</strong> <code>CC = E - N + 2P</code> (calculated via AST decision node branches: if, while, for, and, or).</li>
            <li><strong>Cognitive Complexity:</strong> Evaluates mental burden based on nesting level depth increments.</li>
            <li><strong>Halstead Volume:</strong> <code>V = (N1 + N2) * log2(n1 + n2)</code> from distinct & total operators and operands.</li>
            <li><strong>Maintainability Index:</strong> <code>MI = max(0, (171 - 5.2*ln(V) - 0.23*CC - 16.2*ln(LOC)) * 100 / 171)</code>. Target &ge; 65.0.</li>
          </ul>
        </div>
      </div>
    </div>
  </main>

  <script>
    // Tab switching
    function switchTab(tabId) {
      document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
      document.querySelectorAll('.nav-tab').forEach(el => {
        el.classList.remove('active');
        el.removeAttribute('aria-current');
      });
      const target = document.getElementById(tabId);
      if (target) target.classList.add('active');
      const activeButton = document.getElementById('tab-btn-' + tabId.replace('-tab', ''));
      if (activeButton) {
        activeButton.classList.add('active');
        activeButton.setAttribute('aria-current', 'page');
      }
    }

    // Repo Mode switching (Upload vs URL)
    function switchRepoMode(mode) {
      const btnUpload = document.getElementById('mode-btn-upload');
      const btnUrl = document.getElementById('mode-btn-url');
      const containerUpload = document.getElementById('mode-upload-container');
      const containerUrl = document.getElementById('mode-url-container');
      const alertZone = document.getElementById('repo-alert-zone');
      invalidateRepositoryResults();
      notify(alertZone, '');

      if (mode === 'upload') {
        btnUpload.classList.add('active-mode');
        btnUrl.classList.remove('active-mode');
        containerUpload.style.display = 'block';
        containerUrl.style.display = 'none';
      } else {
        btnUrl.classList.add('active-mode');
        btnUpload.classList.remove('active-mode');
        containerUpload.style.display = 'none';
        containerUrl.style.display = 'block';
      }
      btnUpload.setAttribute('aria-pressed', String(mode === 'upload'));
      btnUrl.setAttribute('aria-pressed', String(mode === 'url'));
    }

    // Selected files state
    let selectedFiles = [];
    let snippetRequestId = 0;
    let repositoryRequestId = 0;
    let repositoryIssues = [];

    function notify(zone, message, kind = 'error') {
      zone.replaceChildren();
      if (!message) return;
      const box = document.createElement('div');
      box.className = 'status-notice ' + kind;
      box.textContent = message;
      zone.appendChild(box);
    }

    function clearRepositoryResults() {
      document.getElementById('repo-results').style.display = 'none';
      repositoryIssues = [];
      document.getElementById('repo-issues-list').replaceChildren();
    }

    function clearSnippetResults(message) {
      document.getElementById('snippet-results').style.display = 'none';
      const placeholder = document.getElementById('snippet-results-placeholder');
      placeholder.style.display = 'flex';
      placeholder.textContent = message;
    }

    function invalidateSnippetResults(message) {
      snippetRequestId++;
      const button = document.getElementById('snippet-btn');
      button.disabled = false;
      document.getElementById('snippet-btn-text').textContent = 'Analyze & Refactor Code';
      clearSnippetResults(message);
    }

    function invalidateRepositoryResults() {
      repositoryRequestId++;
      clearRepositoryResults();
      document.getElementById('repo-btn').disabled = false;
      document.getElementById('repo-btn-text').textContent = 'Run SpotAI Review';
      document.getElementById('upload-btn').disabled = selectedFiles.length === 0;
      document.getElementById('upload-btn-text').textContent = selectedFiles.length
        ? `Quét ${selectedFiles.length} file đã chọn` : 'Quét các File đã Tải lên';
    }

    function beginRepositoryRequest(zone) {
      repositoryRequestId++;
      clearRepositoryResults();
      notify(zone, 'Đang phân tích repository...', 'info');
      return repositoryRequestId;
    }

    function handleFileSelect(e) {
      const files = Array.from(e.target.files);
      addFiles(files);
      e.target.value = '';
    }

    function addFiles(files) {
      const invalid = files.find(file => !/\.(java|py|zip)$/i.test(file.name));
      if (invalid) {
        notify(document.getElementById('repo-alert-zone'), 'Chỉ hỗ trợ tệp .java, .py hoặc .zip.');
        return;
      }
      const candidate = [...selectedFiles];
      for (const file of files) {
        if (!candidate.some(existing => existing.name.toLowerCase() === file.name.toLowerCase())) {
          candidate.push(file);
        }
      }
      const totalSize = candidate.reduce((sum, file) => sum + file.size, 0);
      if (totalSize > 20 * 1024 * 1024) {
        notify(document.getElementById('repo-alert-zone'), 'Tổng dung lượng tải lên vượt quá 20 MB.');
        return;
      }
      selectedFiles = candidate;
      invalidateRepositoryResults();
      notify(document.getElementById('repo-alert-zone'), '');
      renderFileChips();
    }

    function removeFile(index) {
      selectedFiles.splice(index, 1);
      invalidateRepositoryResults();
      renderFileChips();
    }

    function renderFileChips() {
      const chipsEl = document.getElementById('file-chips');
      const uploadBtn = document.getElementById('upload-btn');
      
      if (selectedFiles.length === 0) {
        chipsEl.innerHTML = '';
        uploadBtn.disabled = true;
        document.getElementById('upload-btn-text').innerText = "Quét các File đã Tải lên";
        return;
      }

      uploadBtn.disabled = false;
      document.getElementById('upload-btn-text').innerText = `Quét ${selectedFiles.length} file đã chọn`;

      let html = '';
      selectedFiles.forEach((file, idx) => {
        const sizeKb = (file.size / 1024).toFixed(1);
        html += `
          <div class="file-chip">
            <span>📄 ${escapeHtml(file.name)} (${sizeKb} KB)</span>
            <button type="button" class="file-chip-remove" aria-label="Xóa ${escapeHtml(file.name)}" onclick="removeFile(${idx});">&times;</button>
          </div>
        `;
      });
      chipsEl.innerHTML = html;
    }

    // Setup Drag and Drop events for Drop Zone
    function initDropZone() {
      const dropZone = document.getElementById('drop-zone');
      if (!dropZone) return;

      ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
          e.preventDefault();
          e.stopPropagation();
          dropZone.classList.add('dragover');
        }, false);
      });

      ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
          e.preventDefault();
          e.stopPropagation();
          dropZone.classList.remove('dragover');
        }, false);
      });

      dropZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = Array.from(dt.files);
        addFiles(files);
      }, false);
    }

    // Setup Drag and Drop for Playground textarea
    function initPlaygroundDrop() {
      const editor = document.getElementById('snippet-code');
      if (!editor) return;

      ['dragenter', 'dragover'].forEach(eventName => {
        editor.addEventListener(eventName, (e) => {
          e.preventDefault();
          e.stopPropagation();
          editor.classList.add('dragover');
        }, false);
      });

      ['dragleave', 'drop'].forEach(eventName => {
        editor.addEventListener(eventName, (e) => {
          e.preventDefault();
          e.stopPropagation();
          editor.classList.remove('dragover');
        }, false);
      });

      editor.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = Array.from(dt.files);
        if (files.length > 0) {
          const file = files[0];
          const lower = file.name.toLowerCase();
          const langSel = document.getElementById('snippet-lang');
          if (lower.endsWith('.java')) {
            langSel.value = 'java';
          } else if (lower.endsWith('.py')) {
            langSel.value = 'python';
          } else {
            notify(document.getElementById('snippet-alert-zone'), 'Playground chỉ hỗ trợ tệp .java hoặc .py.');
            return;
          }
          if (file.size > 1024 * 1024) {
            notify(document.getElementById('snippet-alert-zone'), 'Tệp vượt quá giới hạn 1 MB.');
            return;
          }
          const reader = new FileReader();
          reader.onload = function(evt) {
            editor.value = evt.target.result;
            runSnippetAnalysis();
          };
          reader.readAsText(file);
        }
      }, false);
    }

    // Quick samples
    const samples = {
      sql_java: `public class OrderDao {
    public void findOrder(Connection conn, String orderId) throws SQLException {
        String query = "SELECT * FROM orders WHERE id = '" + orderId + "'";
        Statement stmt = conn.createStatement();
        ResultSet rs = stmt.executeQuery(query);
        while (rs.next()) {
            String customer = rs.getString("customer");
            if (customer.equals("VIP")) {
                System.out.println("VIP Customer");
            }
        }
    }
}`,
      nested_java: `public class ComplexCalculator {
    public int compute(int[][][] matrix, int flag) {
        int total = 0;
        if (flag > 0) {
            for (int i = 0; i < matrix.length; i++) {
                for (int j = 0; j < matrix[i].length; j++) {
                    for (int k = 0; k < matrix[i][j].length; k++) {
                        if (matrix[i][j][k] > 0) {
                            if (flag == 1 || flag == 2) {
                                total += matrix[i][j][k] * 2;
                            } else {
                                total += matrix[i][j][k];
                            }
                        }
                    }
                }
            }
        }
        return total;
    }
}`,
      param_py: `def create_user_profile(username, email, phone, address, city, country, postal_code, role, is_active):
    profile = {
        "user": username,
        "email": email,
        "location": f"{city}, {country}",
        "active": is_active
    }
    return profile
`,
      clean_py: `from dataclasses import dataclass

@dataclass
class UserProfile:
    username: str
    email: str
    city: str
    country: str
    is_active: bool = True

def get_profile_summary(profile: UserProfile) -> str:
    status = "Active" if profile.is_active else "Inactive"
    return f"{profile.username} ({profile.email}) - {status}"
`
    };

    function loadSample(key) {
      const code = samples[key];
      if (!code) return;
      document.getElementById('snippet-code').value = code;
      const langSel = document.getElementById('snippet-lang');
      if (key.includes('_py')) {
        langSel.value = 'python';
      } else {
        langSel.value = 'java';
      }
      notify(document.getElementById('snippet-alert-zone'), '');
      invalidateSnippetResults('Mã mẫu đã được tải. Chọn “Analyze & Refactor Code” để phân tích.');
    }

    function onLangChange() {
      // The user's editor contents remain intact when changing languages.
      notify(document.getElementById('snippet-alert-zone'), '');
      invalidateSnippetResults('Ngôn ngữ đã đổi. Nhấn Analyze để phân tích code hiện tại.');
    }

    // Snippet review
    async function runSnippetAnalysis() {
      const code = document.getElementById('snippet-code').value;
      const language = document.getElementById('snippet-lang').value;
      const btn = document.getElementById('snippet-btn');
      const btnText = document.getElementById('snippet-btn-text');
      const alertZone = document.getElementById('snippet-alert-zone');
      const requestId = ++snippetRequestId;
      notify(alertZone, '');

      if (!code.trim()) {
        notify(alertZone, 'Vui lòng nhập hoặc dán mã nguồn trước khi phân tích.');
        document.getElementById('snippet-code').focus();
        return;
      }
      if (new Blob([code]).size > 1024 * 1024) {
        notify(alertZone, 'Đoạn code vượt quá giới hạn 1 MB.');
        return;
      }

      btn.disabled = true;
      btnText.innerHTML = '<span class="spinner"></span> Analyzing...';
      clearSnippetResults('Đang phân tích mã nguồn...');

      try {
        const resp = await fetch('/api/analyze-snippet', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ code, language })
        });
        const data = await resp.json();
        if (requestId !== snippetRequestId) return;
        if (!resp.ok) throw new Error(data.detail || data.message || 'Snippet analysis failed.');

        if (data.status !== 'success') {
          notify(alertZone, data.message || 'Không thể phân tích mã nguồn.');
          return;
        }

        // Show results
        document.getElementById('snippet-results-placeholder').style.display = 'none';
        document.getElementById('snippet-results').style.display = 'block';

        const summary = data.summary || {};
        document.getElementById('snip-cc').innerText = summary.max_cc ?? '-';
        document.getElementById('snip-mi').innerText = summary.average_mi !== undefined ? summary.average_mi + '/100' : '-';
        document.getElementById('snip-issues-count').innerText = data.issues ? data.issues.length : 0;

        let issuesHtml = '';
        if (data.issues && data.issues.length > 0) {
          data.issues.forEach(iss => {
            const sevBadge = ['HIGH', 'CRITICAL'].includes(iss.severity) ? 'badge-high' : (iss.severity === 'MEDIUM' ? 'badge-medium' : 'badge-low');
            issuesHtml += `
              <div style="margin-bottom:8px; display:flex; align-items:flex-start; gap:8px;">
                <span class="badge ${sevBadge}">${escapeHtml(iss.severity)}</span>
                <div>
                  <strong>${escapeHtml(iss.type)}:</strong> <span style="color:var(--text-muted); font-size:0.83rem;">${escapeHtml(iss.message)}</span>
                  <div style="font-size:0.75rem;color:var(--text-muted)">Line ${escapeHtml(iss.start_line)}–${escapeHtml(iss.end_line)}</div>
                  ${iss.code_snippet ? `<pre class="diff-block"><code>${escapeHtml(iss.code_snippet)}</code></pre>` : ''}
                </div>
              </div>
            `;
          });
        } else {
          issuesHtml = '<div style="color:var(--success); font-size:0.85rem;">✓ No critical smells detected! Code conforms to quality rules.</div>';
        }
        document.getElementById('snip-issues-list').innerHTML = issuesHtml;

        const ai = (data.issues || []).find(issue => issue.ai_explanation) || {};
        document.getElementById('snip-ai-explanation').innerText = (ai.ai_provider || 'Static analysis') + ': ' + (ai.ai_explanation || 'Không phát hiện vấn đề cần refactor.');
        document.getElementById('snip-ai-limitations').innerText = ai.ai_limitations || '';
        document.getElementById('snip-diff').innerText = ai.ai_refactored_code || '// No changes needed.';

      } catch (err) {
        if (requestId === snippetRequestId) notify(alertZone, 'Lỗi phân tích: ' + err.message);
      } finally {
        if (requestId === snippetRequestId) {
          btn.disabled = false;
          btnText.innerText = "Analyze & Refactor Code";
        }
      }
    }

    // Shared report renderer
    function renderReportData(data, alertZone) {
      if (data.status === 'no_supported_files') {
        notify(alertZone, data.message || 'Không tìm thấy tệp Python/Java.', 'warning');
        clearRepositoryResults();
        return;
      }

      if (data.status !== 'success' || !data.report) {
        notify(alertZone, data.message || 'Không thể phân tích repository.');
        clearRepositoryResults();
        return;
      }

      notify(alertZone, 'Phân tích hoàn tất.', 'info');
      const rep = data.report;
      document.getElementById('repo-results').style.display = 'block';

      const qgPassed = rep.quality_gate_passed;
      const qgEl = document.getElementById('res-qg');
      qgEl.innerText = qgPassed ? 'PASSED' : 'FAILED';
      qgEl.style.color = qgPassed ? 'var(--success)' : 'var(--danger)';
      document.getElementById('card-qg').className = 'metric-card ' + (qgPassed ? 'good' : 'danger');

      document.getElementById('res-files').innerText = rep.files_scanned;
      document.getElementById('res-loc').innerText = rep.total_loc + ' Lines of Code';
      document.getElementById('res-cc').innerText = rep.average_cc + ' / ' + rep.max_cc;
      document.getElementById('res-mi').innerText = rep.average_mi + ' / 100';
      document.getElementById('res-issues-count').innerText = rep.issues.length;

      const safeDashboard = /^\/dashboard\/[A-Za-z0-9_-]+$/.test(data.dashboard_url || '') ? data.dashboard_url : '';
      const reportId = safeDashboard.split('/').pop();
      document.getElementById('btn-full-dashboard').href = safeDashboard || '#';
      document.getElementById('btn-report-json').href = reportId ? `/reports/${reportId}/json` : '#';
      document.getElementById('btn-report-sarif').href = reportId ? `/reports/${reportId}/sarif` : '#';

      let issuesHtml = '';
      repositoryIssues = rep.issues || [];
      repositoryIssues.forEach((iss, idx) => {
        const sevBadge = ['HIGH', 'CRITICAL'].includes(iss.severity) ? 'badge-high' : (iss.severity === 'MEDIUM' ? 'badge-medium' : 'badge-low');
        issuesHtml += `
          <div class="issue-item">
            <button type="button" class="issue-header" aria-expanded="false" aria-controls="repo-issue-${idx}" onclick="toggleDetails(this, 'repo-issue-${idx}')">
              <span style="display:flex; align-items:center; gap:10px;">
                <span class="badge ${sevBadge}">${escapeHtml(iss.severity)}</span>
                <strong>${escapeHtml(iss.smell_or_bug_type)}</strong>
                <span style="color:var(--text-muted); font-size:0.8rem;"><code>${escapeHtml(iss.file_path)}:${escapeHtml(iss.start_line)}</code></span>
              </span>
              <span style="color:var(--accent); font-size:0.8rem;">Details ▼</span>
            </button>
            <div class="issue-body" id="repo-issue-${idx}" style="display:none;">
              <p><strong>Message:</strong> ${escapeHtml(iss.message)}</p>
              <pre class="diff-block"><code>${escapeHtml(iss.code_snippet || '')}</code></pre>
              ${iss.ai_explanation ? `
                <p style="margin-top:10px;"><strong>Suggestion (${escapeHtml(iss.ai_provider || 'Offline')}):</strong> ${escapeHtml(iss.ai_explanation)}</p>
                <pre class="diff-block"><code>${escapeHtml(iss.ai_refactored_code || '')}</code></pre>
                ${iss.ai_limitations ? `<div class="limitations-alert">${escapeHtml(iss.ai_limitations)}</div>` : ''}
              ` : ''}
            </div>
          </div>
        `;
      });
      document.getElementById('repo-issues-list').innerHTML = issuesHtml;
      if (!repositoryIssues.length) document.getElementById('repo-issues-list').innerHTML = '<div class="status-notice">Không phát hiện vấn đề nào với cấu hình hiện tại.</div>';
      filterRepositoryIssues();
    }

    function filterRepositoryIssues() {
      const severity = document.getElementById('issue-filter-severity').value;
      const query = document.getElementById('issue-filter-search').value.trim().toLocaleLowerCase();
      let visible = 0;
      repositoryIssues.forEach((issue, index) => {
        const matchesSeverity = severity === 'all' || issue.severity === severity;
        const searchable = [issue.file_path, issue.smell_or_bug_type, issue.message].join(' ').toLocaleLowerCase();
        const show = matchesSeverity && searchable.includes(query);
        const row = document.getElementById('repo-issue-' + index);
        if (row) row.parentElement.hidden = !show;
        if (show) visible++;
      });
      document.getElementById('issue-filter-count').textContent = `${visible}/${repositoryIssues.length} vấn đề`;
    }

    // Upload & Analyze execution
    async function runUploadAnalysis() {
      const alertZone = document.getElementById('repo-alert-zone');
      const btn = document.getElementById('upload-btn');
      const btnText = document.getElementById('upload-btn-text');
      const milestone = document.getElementById('upload-milestone').value;

      if (selectedFiles.length === 0) {
        notify(alertZone, 'Vui lòng chọn ít nhất một tệp .java, .py hoặc .zip.');
        document.getElementById('file-upload-input').focus();
        return;
      }

      const requestId = beginRepositoryRequest(alertZone);
      btn.disabled = true;
      btnText.innerHTML = '<span class="spinner"></span> Đang tải lên và phân tích mã nguồn...';

      try {
        const formData = new FormData();
        selectedFiles.forEach(f => {
          formData.append('files', f);
        });
        formData.append('milestone', milestone);

        const resp = await fetch('/api/upload-and-analyze', {
          method: 'POST',
          body: formData
        });
        const data = await resp.json();
        if (requestId !== repositoryRequestId) return;
        if (!resp.ok) throw new Error(data.detail || data.message || 'Upload failed.');
        renderReportData(data, alertZone);
      } catch (err) {
        if (requestId === repositoryRequestId) notify(alertZone, 'Lỗi gửi file: ' + err.message);
      } finally {
        if (requestId === repositoryRequestId) {
          btn.disabled = false;
          btnText.innerText = `Quét ${selectedFiles.length} file đã chọn`;
        }
      }
    }

    // URL / Local path analysis
    async function runRepoAnalysis() {
      const repo = document.getElementById('repo-input').value.trim();
      const milestone = parseInt(document.getElementById('repo-milestone').value);
      const btn = document.getElementById('repo-btn');
      const btnText = document.getElementById('repo-btn-text');
      const alertZone = document.getElementById('repo-alert-zone');

      if (!repo) {
        notify(alertZone, 'Vui lòng nhập đường dẫn repository hoặc GitHub URL.');
        document.getElementById('repo-input').setAttribute('aria-invalid', 'true');
        document.getElementById('repo-input').focus();
        return;
      }

      document.getElementById('repo-input').setAttribute('aria-invalid', 'false');
      const requestId = beginRepositoryRequest(alertZone);
      btn.disabled = true;
      btnText.innerHTML = '<span class="spinner"></span> Scanning Repository...';

      try {
        const resp = await fetch('/api/analyze-repo', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ repo, milestone })
        });
        const data = await resp.json();
        if (requestId !== repositoryRequestId) return;
        if (!resp.ok) throw new Error(data.detail || data.message || 'Repository analysis failed.');
        renderReportData(data, alertZone);
      } catch (err) {
        if (requestId === repositoryRequestId) notify(alertZone, 'Lỗi phân tích repository: ' + err.message);
      } finally {
        if (requestId === repositoryRequestId) {
          btn.disabled = false;
          btnText.innerText = "Run SpotAI Review";
        }
      }
    }

    function toggleDetails(button, id) {
      const el = document.getElementById(id);
      const expanded = button.getAttribute('aria-expanded') === 'true';
      el.style.display = expanded ? 'none' : 'block';
      button.setAttribute('aria-expanded', String(!expanded));
    }

    function escapeHtml(str) {
      return String(str ?? '').replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }

    // Listen for messages from VS Code Extension Webview host
    window.addEventListener('message', function(event) {
      // The iframe receives instructions exclusively from its embedding VS Code webview.
      if (event.source !== window.parent || window.parent === window) return;
      const trustedOrigin = event.origin === window.location.origin ||
        /^https:\/\/[a-z0-9-]+\.vscode-webview\.net$/.test(event.origin) ||
        event.origin.startsWith('vscode-webview://');
      if (!trustedOrigin) return;
      const msg = event.data;
      if (!msg || typeof msg !== 'object' || typeof msg.command !== 'string') return;
      if (msg.command === 'loadSnippet') {
        if (typeof msg.code !== 'string' || !['python', 'java'].includes(msg.language)) return;
        switchTab('playground-tab');
        if (msg.language) {
          const langSel = document.getElementById('snippet-lang');
          if (langSel) {
            langSel.value = msg.language === 'python' ? 'python' : 'java';
          }
        }
        if (msg.code) {
          document.getElementById('snippet-code').value = msg.code;
          runSnippetAnalysis();
        }
      } else if (msg.command === 'loadRepo') {
        switchTab('repo-tab');
        switchRepoMode('url');
        if (msg.path) {
          document.getElementById('repo-input').value = msg.path;
          runRepoAnalysis();
        }
      }
    });

    // Initialize drop zones & default sample on load
    window.onload = function() {
      initDropZone();
      initPlaygroundDrop();
      loadSample('sql_java');
    };
  </script>
</body>
</html>"""


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print(f"Starting SpotAI-Review Web Server on http://localhost:{port}")
    uvicorn.run("spotai.web_server:app", host="127.0.0.1", port=port, reload=False)
