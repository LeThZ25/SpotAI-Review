"""
Repo Resolver Module (SOLID - Single Responsibility Principle)
Handles resolving repository paths:
- Local directory paths (checked for existence)
- Remote Git repository URLs (GitHub, GitLab, Bitbucket) via shallow clone (--depth 1)
"""
import os
import re
import shutil
import stat
import subprocess
import time
from typing import Tuple


class RepoResolverError(Exception):
    """User-friendly exception for repository resolution issues."""
    pass


class RepoResolver:
    """Resolves local paths or clones remote Git repositories into a temporary workspace."""

    GIT_URL_PATTERNS = [
        r"^https?://",
        r"^git@",
        r"^ssh://",
        r"\.git$",
    ]

    def __init__(self, temp_base_dir: str = "temp_repos"):
        self.temp_base_dir = temp_base_dir

    @classmethod
    def is_git_url(cls, target: str) -> bool:
        """Check if target string looks like a remote Git URL."""
        if not target:
            return False
        target_clean = target.strip()
        for pattern in cls.GIT_URL_PATTERNS:
            if re.search(pattern, target_clean, re.IGNORECASE):
                return True
        return False

    @staticmethod
    def extract_repo_name(url_or_path: str) -> str:
        """Extract a clean repository name from URL or local path."""
        cleaned = url_or_path.strip().rstrip("/\\")
        if cleaned.endswith(".git"):
            cleaned = cleaned[:-4]
        name = os.path.basename(cleaned)
        # Fallback if name is empty or weird
        if not name:
            name = "cloned_repo"
        # Sanitize for filesystem safety
        name = re.sub(r'[\\/*?:"<>|]', "_", name)
        return name

    def resolve(self, repo_input: str) -> Tuple[str, bool, str]:
        """
        Resolve repository path.
        Returns:
            Tuple of (resolved_local_path, is_temporary, repo_name)
        Raises:
            RepoResolverError if invalid or clone fails.
        """
        if not repo_input or not repo_input.strip():
            raise RepoResolverError("Đường dẫn repository không được để trống.")

        target = repo_input.strip()

        # Case 1: Remote Git URL
        if self.is_git_url(target):
            return self._clone_remote_repo(target)

        # Case 2: Local directory path
        abs_path = os.path.abspath(target)
        if not os.path.exists(abs_path):
            raise RepoResolverError(
                f"Thư mục repository cục bộ không tồn tại: '{target}'\n"
                f"(Đường dẫn tuyệt đối: {abs_path})\n"
                f"Vui lòng kiểm tra lại đường dẫn hoặc truyền URL GitHub hợp lệ (bắt đầu bằng https://)."
            )
        if not os.path.isdir(abs_path):
            raise RepoResolverError(
                f"Đường dẫn được cung cấp là tệp tin, không phải thư mục repository: '{target}'"
            )

        repo_name = self.extract_repo_name(abs_path)
        return abs_path, False, repo_name

    def _clone_remote_repo(self, git_url: str) -> Tuple[str, bool, str]:
        """Clone a remote repository with --depth 1 to maximize download speed."""
        # Check if git is available
        if not shutil.which("git"):
            raise RepoResolverError(
                "Lỗi: Không tìm thấy công cụ 'git' trong hệ thống (PATH).\n"
                "Để tự động tải repo từ GitHub, vui lòng cài đặt Git và thử lại."
            )

        repo_name = self.extract_repo_name(git_url)
        timestamp = int(time.time())
        clone_folder_name = f"{repo_name}_{timestamp}"
        target_dir = os.path.abspath(os.path.join(self.temp_base_dir, clone_folder_name))

        os.makedirs(self.temp_base_dir, exist_ok=True)

        print(f"\n[INFO] Remote Git URL detected: {git_url}")
        print(f"[INFO] Shallow cloning (--depth 1) into temporary directory: {target_dir}")

        cmd = [
            "git",
            "clone",
            "--depth", "1",
            "--single-branch",
            git_url,
            target_dir
        ]

        try:
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,  # 3 minutes timeout
                check=False
            )

            if process.returncode != 0:
                err_msg = process.stderr.strip() or process.stdout.strip()
                # Clean up if partial clone left behind
                self.cleanup(target_dir)
                raise RepoResolverError(
                    f"Failed to clone repository from '{git_url}'.\n"
                    f"Git error details: {err_msg}\n"
                    f"Please check the repository URL, network connection, or repository permissions."
                )

            print(f"[INFO] Clone completed successfully! Proceeding with code analysis...\n")
            return target_dir, True, repo_name

        except subprocess.TimeoutExpired:
            self.cleanup(target_dir)
            raise RepoResolverError(
                f"Timeout (180s) expired while cloning repository from '{git_url}'.\n"
                f"Please check network connection."
            )
        except Exception as e:
            if not isinstance(e, RepoResolverError):
                self.cleanup(target_dir)
                raise RepoResolverError(f"Unexpected error while cloning repository: {str(e)}")
            raise

    @staticmethod
    def cleanup(dir_path: str) -> bool:
        """Safely remove temporary directory, handling Windows read-only git file locks."""
        if not dir_path or not os.path.exists(dir_path):
            return True

        def _handle_remove_readonly(func, path, exc_info):
            try:
                os.chmod(path, stat.S_IWRITE)
                func(path)
            except Exception:
                pass

        try:
            shutil.rmtree(dir_path, onerror=_handle_remove_readonly)
            return True
        except Exception as e:
            print(f"[WARNING] Could not clean up temporary directory '{dir_path}': {e}")
            return False
