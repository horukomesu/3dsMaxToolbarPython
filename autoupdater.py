"""Simple GitHub auto-updater for the 3ds Max toolbar scripts.

This module checks the latest commit of the specified GitHub repository
and, if a newer version is available, downloads the repository archive,
backs up existing files and installs the update.

Usage::

    import autoupdater
    autoupdater.check_for_updates()

Configuration constants can be tweaked below to match the target
repository and local folder layout.
"""

import hashlib
import logging
import os
import shutil
import subprocess
import tempfile
import time
import zipfile
from typing import Optional

import requests

# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------

GITHUB_OWNER = "owner"
GITHUB_REPO = "repo"
GITHUB_BRANCH = "main"

BASE_DIR = os.path.dirname(__file__)
VERSION_PATH = os.path.join(BASE_DIR, "VERSION")
BACKUP_ROOT = os.path.join(BASE_DIR, "backup")
LOG_FILE = os.path.join(BASE_DIR, "update.log")

# ----------------------------------------------------------------------------

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(handler)


# ----------------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------------


def _get_local_version() -> Optional[str]:
    """Return local commit hash from VERSION file or git repo."""
    if os.path.exists(VERSION_PATH):
        try:
            with open(VERSION_PATH, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception as exc:
            logger.error("Failed to read VERSION file: %s", exc)
            return None
    try:
        out = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=BASE_DIR)
        return out.decode().strip()
    except Exception:
        return None


def _write_local_version(version: str) -> None:
    try:
        with open(VERSION_PATH, "w", encoding="utf-8") as f:
            f.write(version.strip())
    except Exception as exc:
        logger.error("Failed to write VERSION file: %s", exc)


def _get_remote_version() -> Optional[str]:
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/commits/{GITHUB_BRANCH}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("sha")
    except Exception as exc:
        logger.error("Failed to fetch remote version: %s", exc)
        return None


def _download_archive(version: str) -> Optional[str]:
    url = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/archive/{version}.zip"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        fd, path = tempfile.mkstemp(suffix=".zip")
        os.close(fd)
        with open(path, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        logger.info("Downloaded archive sha256: %s", sha256.hexdigest())
        return path
    except Exception as exc:
        logger.error("Failed to download archive: %s", exc)
        return None


def _extract_archive(path: str) -> Optional[str]:
    try:
        tmp_dir = tempfile.mkdtemp()
        with zipfile.ZipFile(path) as zf:
            zf.extractall(tmp_dir)
            top = zf.namelist()[0].split("/")[0]
        return os.path.join(tmp_dir, top)
    except Exception as exc:
        logger.error("Failed to extract archive: %s", exc)
        return None


def _backup_and_copy(src_dir: str, dst_dir: str, timestamp: str) -> None:
    for root, _, files in os.walk(src_dir):
        rel = os.path.relpath(root, src_dir)
        dst_root = os.path.join(dst_dir, rel)
        os.makedirs(dst_root, exist_ok=True)
        for name in files:
            src_path = os.path.join(root, name)
            dst_path = os.path.join(dst_root, name)
            if os.path.isfile(dst_path):
                backup_dir = os.path.join(BACKUP_ROOT, timestamp, rel)
                os.makedirs(backup_dir, exist_ok=True)
                shutil.copy2(dst_path, os.path.join(backup_dir, name))
            shutil.copy2(src_path, dst_path)


# ----------------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------------


def check_for_updates(progress_callback=None) -> bool:
    """Check GitHub for a newer version and update if available.

    Parameters
    ----------
    progress_callback : callable, optional
        Function accepting ``(message: str, value: int)`` to report progress
        from 0 to 100.

    Returns
    -------
    bool
        ``True`` if an update was installed.
    """

    if progress_callback is None:
        def progress_callback(msg, val):
            pass

    logger.info("Checking for updates...")
    progress_callback("Checking versions", 0)
    local_version = _get_local_version()
    remote_version = _get_remote_version()
    logger.info("Local version: %s", local_version)
    logger.info("Remote version: %s", remote_version)

    if not remote_version or local_version == remote_version:
        logger.info("Already up to date" if remote_version else "No remote version")
        progress_callback("Up to date", 100)
        return False

    progress_callback("Downloading update", 20)
    archive_path = _download_archive(remote_version)
    if not archive_path:
        progress_callback("Download failed", 100)
        return False
    progress_callback("Extracting", 60)
    extract_dir = _extract_archive(archive_path)
    if not extract_dir:
        os.unlink(archive_path)
        progress_callback("Extraction failed", 100)
        return False

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    try:
        progress_callback("Installing", 80)
        _backup_and_copy(extract_dir, BASE_DIR, timestamp)
        _write_local_version(remote_version)
        progress_callback("Update installed", 100)
        logger.info("Update installed successfully")
        return True
    except Exception as exc:
        logger.error("Failed during update: %s", exc)
        progress_callback("Update failed", 100)
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)
        os.unlink(archive_path)
    return False

