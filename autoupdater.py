"""GitHub auto-update module for script projects.

This module checks the specified GitHub repository for updates based on a
version file and downloads the latest archive when required.
All operations are logged to ``update.log``.
"""

from __future__ import annotations

BASE_DIR = os.path.dirname(__file__)
sys.path.insert(0, BASE_DIR)

import logging
import os
import shutil
import zipfile
from io import BytesIO
from typing import Callable, Optional
import sys

from PySide2 import QtWidgets, QtCore

import requests

# Configurable parameters ----------------------------------------------------
GITHUB_OWNER = "horukomesu"
GITHUB_REPO = "3dsMaxToolbarPython"
BRANCH = "main"
VERSION_FILE = "VERSION"
LOG_FILE = "update.log"
# Environment variable used to skip update when already run by launcher
SKIP_ENV_VAR = "AUTOUPDATER_SKIP"
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


class UpdateThread(QtCore.QThread):
    """Background worker executing :func:`update_logic`."""

    progress = QtCore.Signal(str, int)
    finished_with_result = QtCore.Signal(bool)
    request_confirm = QtCore.Signal(str)
    error = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mutex = QtCore.QMutex()
        self._wait = QtCore.QWaitCondition()
        self._confirm_answer: Optional[bool] = None
        self.result = False

    @QtCore.Slot(bool)
    def confirm_reply(self, answer: bool) -> None:
        self._mutex.lock()
        self._confirm_answer = answer
        self._wait.wakeAll()
        self._mutex.unlock()

    def _confirm(self, message: str) -> bool:
        self._mutex.lock()
        self._confirm_answer = None
        self.request_confirm.emit(message)
        while self._confirm_answer is None:
            self._wait.wait(self._mutex)
        ans = self._confirm_answer
        self._mutex.unlock()
        return bool(ans)

    def _progress(self, msg: str, value: int) -> None:
        self.progress.emit(msg, value)

    def run(self) -> None:
        try:
            self.result = update_logic(self._confirm, self._progress)
        except Exception as exc:  # pragma: no cover - just in case
            self.error.emit(str(exc))
            self.result = False
        self.finished_with_result.emit(self.result)


def _read_local_version() -> str:
    path = os.path.join(BASE_DIR, VERSION_FILE)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read().strip()
    except FileNotFoundError:
        return ""


def fetch_remote_version() -> Optional[str]:
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


def download_repo_zip() -> bytes:
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


def update_logic(confirm: Callable[[str], bool],
                 callback: Optional[ProgressCallback] = None) -> bool:
    """Core workflow used by both UI and CLI wrappers."""
    if os.environ.get(SKIP_ENV_VAR):
        _logger.info("Skipping update due to %s", SKIP_ENV_VAR)
        restore_key_files(confirm, callback)
        if callback:
            callback("Up to date", 100)
        return False
    if callback:
        callback("Checking for updates...", 0)
    _logger.info("Checking for updates...")

    local_version = _read_local_version()
    remote_version = fetch_remote_version()

    _logger.info("Local version: %s", local_version)
    _logger.info("Remote version: %s", remote_version)

    if remote_version is None:
        if callback:
            callback("Failed to fetch remote version", 100)
        restore_key_files(confirm, callback)
        return False

    needs_update = local_version != remote_version
    zip_data = b""
    if needs_update:
        if not confirm("Обнаружено обновление, скачать?"):
            needs_update = False
        else:
            try:
                zip_data = download_repo_zip()
            except Exception as exc:
                _logger.error("Failed to download repository archive: %s", exc)
                if callback:
                    callback("Download failed", 100)
                restore_key_files(confirm, callback)
                return False

    if needs_update:
        if callback:
            callback("Updating...", 50)
        _perform_update(zip_data, remote_version, callback)
        if callback:
            callback("Done", 100)

    # всегда проверяем ключевые файлы
    restore_key_files(confirm, callback)

    if not needs_update and callback:
        callback("Up to date", 100)

    return needs_update


def check_for_updates(callback: Optional[ProgressCallback] = None) -> bool:
    """Check GitHub for a newer version and update if necessary."""

    return update_logic(lambda _msg: True, callback)


def update_with_ui(parent: Optional[QtWidgets.QWidget] = None) -> bool:
    """Run update workflow in a background thread displaying simple UI."""

    dlg = UpdateDialog(parent)
    thread = UpdateThread(dlg)

    def on_progress(msg: str, value: int) -> None:
        dlg.update_status(msg, value)

    def on_confirm(msg: str) -> None:
        reply = QtWidgets.QMessageBox.question(
            parent,
            "Обновление",
            msg,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        thread.confirm_reply(reply == QtWidgets.QMessageBox.Yes)

    result: bool = False

    def on_finished(res: bool) -> None:
        nonlocal result
        result = res
        loop.quit()

    thread.progress.connect(on_progress)
    thread.request_confirm.connect(on_confirm)
    thread.finished_with_result.connect(on_finished)

    dlg.show()
    thread.start()

    loop = QtCore.QEventLoop()
    loop.exec_()

    thread.wait()
    dlg.close()
    return result

# ========================================================================
# KEY FILE CHECK LOGIC
# ========================================================================

def fetch_filelist() -> Optional[list[str]]:
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


def recover_files_from_zip(zip_data: bytes, missing: list[str],
                           callback: Optional[ProgressCallback]) -> list[str]:
    """Extract only ``missing`` files from ``zip_data`` archive."""
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
                if callback:
                    callback(f"Recovered {file}", 0)
            else:
                _logger.error("File %s not found in repo archive!", file)
    return recovered


def restore_key_files(confirm: Callable[[str], bool],
                      callback: Optional[ProgressCallback] = None) -> bool:
    """Ensure key files listed in ``filelist.txt`` exist, recovering if needed."""
    if callback:
        callback("Checking key files...", 0)
    _logger.info("Checking key files...")

    key_files = fetch_filelist()
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
    if not confirm(
        "\n".join(["Обнаружены недостающие файлы:", *missing, "Скачать из репозитория?"])
    ):
        _logger.info("User cancelled recovering missing files.")
        return False

    if callback:
        callback("Recovering missing files...", 50)

    try:
        zip_data = download_repo_zip()
    except Exception as exc:
        _logger.error("Failed to download repository archive: %s", exc)
        if callback:
            callback("Download failed", 100)
        return False

    recovered = recover_files_from_zip(zip_data, missing, callback)
    if callback:
        callback("Recovered missing files", 100)
    _logger.info("Recovered files: %s", recovered)
    return not _check_key_files_exist(key_files)

def check_key_files_and_recover(parent=None, callback: Optional[ProgressCallback] = None) -> bool:
    """UI wrapper for :func:`restore_key_files`."""
    def confirm(message: str) -> bool:
        if parent is None:
            return True
        reply = QtWidgets.QMessageBox.question(
            parent,
            "Восстановление файлов",
            message,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        return reply == QtWidgets.QMessageBox.Yes

    return restore_key_files(confirm, callback)

# ========================================================================




def main() -> None:
    """Command line entry point for the updater."""
    print("Checking for updates...")
    try:
        update_logic(lambda _msg: True, lambda m, v: print(f"{m} ({v}%)"))
    except Exception as exc:  # pragma: no cover - just in case
        print(f"Update failed: {exc}")
        return


if __name__ == "__main__":
    from PySide2 import QtWidgets
    import sys
    import os

    BASE_DIR = os.path.dirname(__file__)
    sys.path.insert(0, BASE_DIR)

    # Запуск апдейта
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)

    result = update_with_ui()

    # После апдейта — запуск ToolbarMain.py
    try:
        import ToolbarMain
        if hasattr(ToolbarMain, 'main'):
            ToolbarMain.main()
        # Если нужен запуск конкретной функции — поменяй на свою
    except Exception as exc:
        import traceback
        print("Ошибка запуска ToolbarMain.py:", exc)
        traceback.print_exc()

