"""GitHub auto-update module for script projects.

This module checks the specified GitHub repository for updates based on a
version file and downloads the latest archive when required.
All operations are logged to ``update.log``.
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
GITHUB_OWNER = "horukomesu"
GITHUB_REPO = "3dsMaxToolbarPython"
BRANCH = "main"
VERSION_FILE = "VERSION"
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


def _should_ignore(path: str) -> bool:
    """Return ``True`` for auxiliary files that should be ignored."""
    return (
        "__pycache__" in path.split("/") or path.endswith(".pyc")
    )


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
            rel = member[len(top) + 1 : ]
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
        # Проверяем ключевые файлы даже если архив не скачался!
        check_key_files_and_recover(callback)
        return False

    if remote_version is None:
        if callback:
            callback("Failed to fetch remote version", 100)
        check_key_files_and_recover(callback)
        return False

    if local_version != remote_version:
        if callback:
            callback("Updating...", 50)
        _perform_update(zip_data, remote_version, callback)
        if callback:
            callback("Done", 100)
        # После обновления — сразу проверяем ключевые файлы
        check_key_files_and_recover(callback)
        return True

    if callback:
        callback("Up to date", 100)
    # Даже если всё up-to-date — всё равно проверяем ключевые файлы
    check_key_files_and_recover(callback)
    return False


def update_with_ui(parent: Optional[QtWidgets.QWidget] = None) -> bool:
    local_version = _read_local_version()
    remote_version = _fetch_remote_version()

    needs_update = remote_version is not None and local_version != remote_version

    if not needs_update:
        # Даже если обновления нет — проверим ключевые файлы
        check_key_files_and_recover()
        return False


    # Запрашиваем подтверждение!
    question = "Обнаружено обновление, скачать?"

    reply = QtWidgets.QMessageBox.question(
        parent,
        "Обновление",
        question,
        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
    )
    if reply != QtWidgets.QMessageBox.Yes:
        return False

    # Только теперь скачиваем архив!
    try:
        zip_data = _download_repo_zip()
    except Exception as exc:
        _logger.error("Failed to download repository archive: %s", exc)
        return False

    dlg = UpdateDialog(parent)
    dlg.show()

    def cb(msg: str, value: int) -> None:
        dlg.update_status(msg, value)

    cb("Updating...", 0)
    _perform_update(zip_data, remote_version or "", cb)
    dlg.close()
    return needs_update

# ========================================================================
# KEY FILE CHECK LOGIC
# ========================================================================

def _fetch_filelist() -> Optional[list[str]]:
    """Скачать и вернуть список ключевых файлов из filelist.txt на GitHub."""
    url = (
        f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/"
        f"{BRANCH}/filelist.txt"
    )
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        # Разделяем по строкам и убираем пустые
        return [line.strip() for line in response.text.splitlines() if line.strip()]
    except Exception as exc:
        _logger.error("Failed to fetch filelist.txt: %s", exc)
        return None

def _check_key_files_exist(key_files: list[str]) -> list[str]:
    """Проверяет наличие ключевых файлов, возвращает список отсутствующих."""
    missing = []
    for file in key_files:
        if not os.path.exists(os.path.join(BASE_DIR, file)):
            missing.append(file)
    return missing

def check_key_files_and_recover(callback: Optional[ProgressCallback] = None) -> bool:
    """
    Проверяет наличие ключевых файлов из filelist.txt в репозитории GitHub
    и восстанавливает отсутствующие файлы из архива репозитория.

    Returns True если все ключевые файлы теперь на месте.
    """
    if callback:
        callback("Checking key files...", 0)
    _logger.info("Checking key files...")

    key_files = _fetch_filelist()
    if key_files is None:
        if callback:
            callback("Failed to fetch filelist", 100)
        _logger.error("No key file list fetched!")
        return False

    missing = _check_key_files_exist(key_files)
    if not missing:
        if callback:
            callback("All key files present", 100)
        _logger.info("All key files are present.")
        return True

    _logger.warning("Missing key files: %s", missing)
    if callback:
        callback("Recovering missing files...", 50)

    # Скачиваем zip и восстанавливаем только недостающие
    try:
        zip_data = _download_repo_zip()
    except Exception as exc:
        _logger.error("Failed to download repository archive: %s", exc)
        if callback:
            callback("Download failed", 100)
        return False

    with zipfile.ZipFile(BytesIO(zip_data)) as zf:
        top = zf.namelist()[0].split("/")[0]
        recovered = []
        for file in missing:
            repo_file = f"{top}/{file.replace(os.sep, '/')}"
            if repo_file in zf.namelist():
                dst = os.path.join(BASE_DIR, file)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with zf.open(repo_file) as src, open(dst, "wb") as out:
                    shutil.copyfileobj(src, out)
                recovered.append(file)
                _logger.info("Recovered missing file: %s", file)
            else:
                _logger.error("File %s not found in repo archive!", file)
        if callback:
            callback("Recovered missing files", 100)
        _logger.info("Recovered files: %s", recovered)
    return not _check_key_files_exist(key_files)  # Проверим что теперь все есть

# ========================================================================

