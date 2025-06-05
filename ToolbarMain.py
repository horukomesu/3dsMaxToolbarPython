import os
import sys
import json

BASE_DIR = os.path.dirname(__file__)
sys.path.insert(0, BASE_DIR)  # Fix: add path before import

from lodkitfilter import apply_filter_from_button_states

from PySide2 import QtWidgets, QtCore
from PySide2.QtUiTools import QUiLoader
from PySide2.QtCore import QFile
import qtmax

SETTINGS_PATH = os.path.join(BASE_DIR, 'settings.json')
UI_PATH = os.path.join(BASE_DIR, 'majestic_main.ui')

def on_apply_filter_clicked():
    apply_filter_from_button_states(get_button_states())


def get_setting(section, key, default=None):
    if not os.path.exists(SETTINGS_PATH):
        return default
    with open(SETTINGS_PATH, 'r') as f:
        data = json.load(f)
    return data.get(section, {}).get(key, default)


def set_setting(section, key, value):
    data = {}
    if os.path.exists(SETTINGS_PATH):
        with open(SETTINGS_PATH, 'r') as f:
            data = json.load(f)
    if section not in data:
        data[section] = {}
    data[section][key] = value
    with open(SETTINGS_PATH, 'w') as f:
        json.dump(data, f, indent=4)


def ensure_settings_file_exists():
    if not os.path.exists(SETTINGS_PATH):
        default_settings = {
            "kits": {
                "Kit0": "stock",
                "Kit1": "restyle",
                "Kit2": "Sport",
                "Kit3": "Tuning",
                "Base": "base",
                "Interior": "interior",
                "Wheel": "wheel"
            }
        }
        with open(SETTINGS_PATH, 'w') as f:
            json.dump(default_settings, f, indent=4)


class MajesticDockWidget(QtWidgets.QDockWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        loader = QUiLoader()
        ui_file = QFile(UI_PATH)
        ui_file.open(QFile.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()
        self.setWidget(self.ui)

        self.setup_buttons_state_logic()
        self.setup_lod_kit_groups()
        self.setup_component_buttons()
        self.sync_lineedits_with_settings()

        for btn_name in ["btnL0", "btnKit0", "btnBase"]:
            btn = self.findChild(QtWidgets.QPushButton, btn_name)
            if btn:
                btn.setChecked(True)

        self.enable_filter_cb = self.findChild(QtWidgets.QCheckBox, "chkEnableFilter")
        if self.enable_filter_cb:
            self.enable_filter_cb.toggled.connect(self.on_enable_filter_toggled)
            try:
                self.obj_frame = self.findChild(QtWidgets.QFrame, "OBJframe")
                if self.obj_frame:
                    self.obj_frame.setEnabled(self.enable_filter_cb.isChecked())
                else:
                    print("[WARN] OBJframe not found in UI")
            except RuntimeError:
                print("[WARN] OBJframe access caused RuntimeError")

        btn_info = self.findChild(QtWidgets.QPushButton, "btnInfo1")
        if btn_info:
            btn_info.clicked.connect(self.show_info_dialog)

    def on_enable_filter_toggled(self, checked):
        try:
            obj_frame = self.findChild(QtWidgets.QFrame, "OBJframe")
            if obj_frame:
                obj_frame.setEnabled(checked)
            else:
                print("[WARN] OBJframe not found in UI")
        except RuntimeError:
            print("[WARN] OBJframe access caused RuntimeError")
        on_apply_filter_clicked()

    def get_button_states(self):
        states = {}
        for name in self.get_all_button_names():
            widget = self.findChild(QtWidgets.QWidget, name)
            if isinstance(widget, (QtWidgets.QPushButton, QtWidgets.QCheckBox)):
                states[name] = widget.isChecked()
        return states

    def get_all_button_names(self):
        # List all button and checkbox names tracked in UI
        return [
            "btnL0", "btnL1", "btnL2", "btnL3",
            "btnKitEmpty", "btnKit0", "btnKit1", "btnKit2", "btnKit3",
            "btnBase", "btnInterior", "btnWheel",
            "chkEnableFilter"
        ]

    def setup_buttons_state_logic(self):
        for btn_name in self.get_all_button_names():
            if btn_name == "chkEnableFilter":
                continue
            btn = self.findChild(QtWidgets.QPushButton, btn_name)
            if btn:
                btn.setCheckable(True)
                btn.clicked.connect(self.make_click_handler())

    def make_click_handler(self):
        def handler(checked):
            on_apply_filter_clicked()
        return handler

    def show_info_dialog(self):
        QtWidgets.QMessageBox.information(
            self,
            "Подсказка",
            "Имя для каждого обвеса или базы машины требуется указать вручную..."
        )

    def setup_lod_kit_groups(self):
        self.lod_group = QtWidgets.QButtonGroup(self)
        self.lod_group.setExclusive(True)
        for name in ["btnL0", "btnL1", "btnL2", "btnL3"]:
            btn = self.findChild(QtWidgets.QPushButton, name)
            if btn:
                self.lod_group.addButton(btn)
        self.lod_group.buttonClicked.connect(on_apply_filter_clicked)

        self.kit_group = QtWidgets.QButtonGroup(self)
        self.kit_group.setExclusive(True)
        for name in ["btnKitEmpty", "btnKit0", "btnKit1", "btnKit2", "btnKit3"]:
            btn = self.findChild(QtWidgets.QPushButton, name)
            if btn:
                self.kit_group.addButton(btn)
        self.kit_group.buttonClicked.connect(on_apply_filter_clicked)

    def setup_component_buttons(self):
        for btn_name in ["btnBase", "btnInterior", "btnWheel"]:
            btn = self.findChild(QtWidgets.QPushButton, btn_name)
            if btn:
                btn.setCheckable(True)

    def sync_lineedits_with_settings(self):
        for key in ["Kit0", "Kit1", "Kit2", "Kit3", "Base", "Interior", "Wheel"]:
            line_edit = self.findChild(QtWidgets.QLineEdit, f"lnedt{key}")
            if line_edit:
                val = get_setting("kits", key, "")
                line_edit.setText(val)
                line_edit.textChanged.connect(lambda text, k=key: set_setting("kits", k, text))

    def closeEvent(self, event):
        global ui_dock_widget
        ui_dock_widget = None
        event.accept()

def main():
    global ui_dock_widget

    ensure_settings_file_exists()

    if ui_dock_widget:
        try:
            ui_dock_widget.close()
        except:
            pass

    parent = qtmax.GetQMaxMainWindow()
    ui_dock_widget = MajesticDockWidget(parent)
    ui_dock_widget.setFloating(True)
    ui_dock_widget.show()

def get_button_states():
    if ui_dock_widget:
        return ui_dock_widget.get_button_states()
    return {}


if __name__ == '__main__':
    ui_dock_widget = None
    main()




# Diagnostics (optional)
print(f"BASE_DIR: {BASE_DIR}")
print(f"sys.path: {sys.path}")
print(f"lodkitfilter.py exists: {os.path.exists(os.path.join(BASE_DIR, 'lodkitfilter.py'))}")
