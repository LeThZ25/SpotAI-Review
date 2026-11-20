"""Bundle the Windows x64 SpotAI web engine for a zero-setup VS Code VSIX.

Build-machine requirements: Windows x64, Python 3.11+ with requirements.txt
and PyInstaller installed. End users do not need Python or these packages.
"""
import platform
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "vscode-extension"
BACKEND_DIR = EXTENSION / "backend" / "spotai_backend"


def build() -> Path:
    if sys.platform != "win32" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise RuntimeError("The self-contained VSIX currently targets Windows x64.")

    try:
        import PyInstaller  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("Install the build tool with: python -m pip install pyinstaller") from exc

    cmd = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--onedir", "--console", "--noupx", "--name", "spotai_backend",
        "--distpath", str(EXTENSION / "backend"),
        "--workpath", str(EXTENSION / ".build" / "work"),
        "--specpath", str(EXTENSION / ".build"),
        "--paths", str(ROOT / "src"),
        "--hidden-import", "spotai.web_server",
        "--collect-submodules", "uvicorn",
        "--collect-submodules", "spotai",
        "--exclude-module", "tkinter",
        "--exclude-module", "matplotlib",
        "--exclude-module", "numpy",
        "--exclude-module", "pandas",
        "--exclude-module", "IPython",
        "--exclude-module", "pytest",
        str(ROOT / "spotai_cli.py"),
    ]
    subprocess.run(cmd, cwd=ROOT, check=True)
    executable = BACKEND_DIR / "spotai_backend.exe"
    if not executable.is_file():
        raise RuntimeError("PyInstaller completed without producing spotai_backend.exe.")
    return executable


if __name__ == "__main__":
    try:
        print("Bundled backend:", build())
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print("Backend build failed:", exc, file=sys.stderr)
        sys.exit(1)
