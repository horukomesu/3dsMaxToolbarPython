"""GitHub auto-update module for script projects.

This module checks the specified GitHub repository for updates based on a
version file and downloads the latest archive when required. It can also
restore missing files by comparing the local directory with the repository
contents. All operations are logged to ``update.log``.
"""

from __future__ import annotations

import logging
import os
import shutil
import zipfile
from io import BytesIO
from typing import Callable, Optional

from PySide2 import QtWidgets

import requests

# Configurable parameters ----------------------------------------------------
# GitHub owner and repository name, e.g. "myuser" and "myrepo"
GITHUB_OWNER = "owner"
GITHUB_REPO = "repo"
# Branch name to fetch
BRANCH = "main"
# Name of the file that stores the commit hash/version
VERSION_FILE = "VERSION"
# Name of the log file
LOG_FILE = "update.log"
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

_logger = logging.getLogger(__name__)
if not _logger.handlers:
    _logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler = logging.FileHandler(os.path.join(BASE_DIR, LOG_FILE), encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    _logger.addHandler(file_handler)
    _logger.addHandler(stream_handler)

ProgressCallback = Callable[[str, int], None]


class UpdateDialog(QtWidgets.QDialog):
    """Simple dialog displaying update progress."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Updating")
        layout = QtWidgets.QVBoxLayout(self)
        self.label = QtWidgets.QLabel("", self)
        self.progress = QtWidgets.QProgressBar(self)
        self.progress.setRange(0, 100)
        layout.addWidget(self.label)
        layout.addWidget(self.progress)

    def update_status(self, msg: str, value: int) -> None:
        self.label.setText(msg)
        self.progress.setValue(value)
        QtWidgets.QApplication.processEvents()


def _read_local_version() -> str:
    path = os.path.join(BASE_DIR, VERSION_FILE)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read().strip()
    except FileNotFoundError:
        return ""


def _fetch_remote_version() -> Optional[str]:
    url = (
        f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/"
        f"{BRANCH}/{VERSION_FILE}"
    )
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        return response.text.strip()
    except Exception as exc:
        _logger.error("Failed to fetch remote version: %s", exc)
        return None


def _download_repo_zip() -> bytes:
    url = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/archive/refs/heads/{BRANCH}.zip"
    _logger.info("Downloading repository archive...")
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return response.content


def _check_missing_files(zip_data: bytes) -> bool:
    """Return ``True`` if any repository file is missing locally."""
    with zipfile.ZipFile(BytesIO(zip_data)) as zf:
        top = zf.namelist()[0].split("/")[0]
        for member in zf.namelist():
            rel = member[len(top) + 1 :]
            if not rel:
                continue
            dst = os.path.join(BASE_DIR, rel)
            if not os.path.exists(dst):
                return True
    return False


def _restore_missing_files(
    zip_data: bytes, callback: Optional[ProgressCallback]
) -> bool:
    """Restore files that are missing locally.

    Returns ``True`` when any file has been restored."""
    restored = False
    with zipfile.ZipFile(BytesIO(zip_data)) as zf:
        top = zf.namelist()[0].split("/")[0]
        members = [m for m in zf.namelist() if m.startswith(top + "/")]
        for member in members:
            rel = member[len(top) + 1 :]
            if not rel:
                continue
            dst = os.path.join(BASE_DIR, rel)
            if not os.path.exists(dst):
                if member.endswith("/"):
                    os.makedirs(dst, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    with zf.open(member) as src, open(dst, "wb") as out:
                        shutil.copyfileobj(src, out)
                restored = True
                _logger.info("Restored %s", rel)
                if callback:
                    callback(f"Restored {rel}", 0)
    return restored


def _perform_update(zip_data: bytes, new_version: str, callback: Optional[ProgressCallback]) -> None:
    _logger.info("Installing update %s", new_version)

    names_to_keep = {os.path.basename(__file__), LOG_FILE}
    for name in os.listdir(BASE_DIR):
        if name in names_to_keep:
            continue
        path = os.path.join(BASE_DIR, name)
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
        except Exception as exc:
            _logger.error("Failed to remove %s: %s", path, exc)

    with zipfile.ZipFile(BytesIO(zip_data)) as zf:
        top = zf.namelist()[0].split("/")[0]
        for member in zf.namelist():
            rel = member[len(top) + 1 :]
            if not rel:
                continue
            dst = os.path.join(BASE_DIR, rel)
            if member.endswith("/"):
                os.makedirs(dst, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with zf.open(member) as src, open(dst, "wb") as out:
                    shutil.copyfileobj(src, out)
            if callback:
                callback(f"Extracting {rel}", 0)

    with open(os.path.join(BASE_DIR, VERSION_FILE), "w", encoding="utf-8") as fh:
        fh.write(new_version)
    _logger.info("Update installed")


def check_for_updates(callback: Optional[ProgressCallback] = None) -> bool:
    """Check GitHub for a newer version and update if necessary.

    Returns ``True`` when an update has been installed.
    """
    if callback:
        callback("Checking for updates...", 0)
    _logger.info("Checking for updates...")

    local_version = _read_local_version()
    remote_version = _fetch_remote_version()

    _logger.info("Local version: %s", local_version)
    _logger.info("Remote version: %s", remote_version)

    try:
        zip_data = _download_repo_zip()
    except Exception as exc:
        _logger.error("Failed to download repository archive: %s", exc)
        if callback:
            callback("Download failed", 100)
        return False

    _restore_missing_files(zip_data, callback)

    if remote_version is None:
        if callback:
            callback("Failed to fetch remote version", 100)
        return False

    if local_version != remote_version:
        if callback:
            callback("Updating...", 50)
        _perform_update(zip_data, remote_version, callback)
        if callback:
            callback("Done", 100)
        return True

    if callback:
        callback("Up to date", 100)
    return False


def update_with_ui(parent: Optional[QtWidgets.QWidget] = None) -> bool:
    """Check for updates and missing files and display a progress dialog.

    Returns ``True`` when an update has been installed. Missing files are
    restored automatically and also trigger the dialog."""

    local_version = _read_local_version()
    remote_version = _fetch_remote_version()

    try:
        zip_data = _download_repo_zip()
    except Exception as exc:
        _logger.error("Failed to download repository archive: %s", exc)
        return False

    missing_files = _check_missing_files(zip_data)
    needs_update = remote_version is not None and local_version != remote_version

    if not missing_files and not needs_update:
        return False

    if needs_update:
        reply = QtWidgets.QMessageBox.question(
            parent,
            "Update Available",
            "\u041e\u0431\u043d\u0430\u0440\u0443\u0436\u0435\u043d\u043e \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u0435, \u0441\u043a\u0430\u0447\u0430\u0442\u044c?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if reply != QtWidgets.QMessageBox.Yes and not missing_files:
            return False
        proceed = reply == QtWidgets.QMessageBox.Yes
    else:
        proceed = True

    if not proceed and missing_files:
        # still restore missing files without full update
        dlg = UpdateDialog(parent)
        dlg.show()

        def cb(msg: str, value: int) -> None:
            dlg.update_status(msg, value)

        _restore_missing_files(zip_data, cb)
        dlg.close()
        return False

    dlg = UpdateDialog(parent)
    dlg.show()

    def cb(msg: str, value: int) -> None:
        dlg.update_status(msg, value)

    if needs_update:
        cb("Updating...", 0)
        _perform_update(zip_data, remote_version or "", cb)
    else:
        _restore_missing_files(zip_data, cb)

    dlg.close()
    return needs_update
