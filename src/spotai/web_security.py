"""Input boundaries for the locally hosted web interface."""
import os
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from fastapi import HTTPException, UploadFile


# The installed VS Code extension keeps generated reports/uploads in its own
# writable storage. The standalone CLI/Web retain their original project root.
PROJECT_ROOT = Path(os.environ.get("SPOTAI_DATA_ROOT") or Path(__file__).resolve().parents[2]).resolve()
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_EXTRACTED_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 1000
CHUNK_BYTES = 1024 * 1024


def is_within(path: os.PathLike | str, root: os.PathLike | str) -> bool:
    """Resolve links before checking containment, including on Windows."""
    resolved = os.path.realpath(path)
    boundary = os.path.realpath(root)
    try:
        return os.path.commonpath((resolved, boundary)) == boundary
    except ValueError:
        # Windows paths on different drives do not have a common path.
        return False


def allowed_local_repository(path: str) -> bool:
    roots = [str(PROJECT_ROOT)]
    roots.extend(x for x in os.environ.get("SPOTAI_ALLOWED_ROOTS", "").split(os.pathsep) if x)
    return any(is_within(path, root) for root in roots)


def validate_github_https(raw_url: str) -> bool:
    try:
        parts = urlsplit(raw_url)
        port = parts.port
    except ValueError:
        return False
    if (parts.scheme != "https" or parts.hostname != "github.com" or port is not None
            or parts.username or parts.password or parts.query or parts.fragment):
        return False
    segments = parts.path.strip("/").split("/")
    if len(segments) != 2:
        return False
    return all(re.fullmatch(r"[A-Za-z0-9_.-]+", item) and item not in (".", "..") for item in segments)


def validate_report_id(name: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{1,100}", name))


def validate_analysis_options(milestone: int, clone_threshold: float, min_clone_lines: int, max_cc: int) -> None:
    if milestone not in (1, 2, 3, 4) or not 0 < clone_threshold <= 1 or min_clone_lines < 2 or max_cc < 1:
        raise HTTPException(status_code=400, detail="Invalid analysis settings. Check milestone, clone threshold, clone lines and CC.")


async def save_upload(file: UploadFile, destination: Path, remaining_bytes: int) -> int:
    size = 0
    with destination.open("xb") as output:
        while chunk := await file.read(CHUNK_BYTES):
            size += len(chunk)
            if size > remaining_bytes:
                raise HTTPException(status_code=413, detail="Upload exceeds the 20 MB limit.")
            output.write(chunk)
    return size


async def count_upload(file: UploadFile, remaining_bytes: int) -> int:
    """Apply the aggregate upload limit even to unsupported extensions."""
    size = 0
    while chunk := await file.read(CHUNK_BYTES):
        size += len(chunk)
        if size > remaining_bytes:
            raise HTTPException(status_code=413, detail="Upload exceeds the 20 MB limit.")
    return size


def extract_zip_safely(zip_path: Path, destination: Path, used_entries: int = 0,
                       used_bytes: int = 0, seen: set[str] | None = None) -> tuple[int, int]:
    """Extract ZIP entries with path, type, count and actual expanded-size checks."""
    if seen is None:
        seen = set()
    try:
        with zipfile.ZipFile(zip_path) as archive:
            for entry in archive.infolist():
                used_entries += 1
                if used_entries > MAX_ARCHIVE_ENTRIES:
                    raise HTTPException(status_code=413, detail="ZIP exceeds 1,000 entries.")
                raw = entry.filename
                parts = PurePosixPath(raw).parts
                if (not raw or raw.startswith(("/", "\\")) or "\\" in raw or ":" in raw
                        or any(part in (".", "..") for part in parts)
                        or stat.S_ISLNK(entry.external_attr >> 16)):
                    raise HTTPException(status_code=400, detail="ZIP contains an unsafe path or symbolic link.")
                target = destination.joinpath(*parts)
                if not is_within(target, destination):
                    raise HTTPException(status_code=400, detail="ZIP entry escapes the upload directory.")
                if entry.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                key = str(target).casefold()
                if key in seen or target.exists():
                    raise HTTPException(status_code=400, detail="ZIP contains duplicate paths.")
                seen.add(key)
                if used_bytes + entry.file_size > MAX_EXTRACTED_BYTES:
                    raise HTTPException(status_code=413, detail="ZIP exceeds 100 MB expanded size.")
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as input_file, target.open("xb") as output_file:
                    while chunk := input_file.read(CHUNK_BYTES):
                        used_bytes += len(chunk)
                        if used_bytes > MAX_EXTRACTED_BYTES:
                            raise HTTPException(status_code=413, detail="ZIP exceeds 100 MB expanded size.")
                        output_file.write(chunk)
    except (zipfile.BadZipFile, EOFError, RuntimeError, ValueError, OSError) as err:
        raise HTTPException(status_code=400, detail="Invalid or damaged ZIP archive.") from err
    return used_entries, used_bytes
