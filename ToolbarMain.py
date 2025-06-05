import os
import sys
import json

BASE_DIR = os.path.dirname(__file__)
sys.path.insert(0, BASE_DIR)

from lodkitfilter import apply_filter_from_button_states, GROUP_TAGS_PATH

from PySide2 import QtWidgets
from PySide2.QtUiTools import QUiLoader
from PySide2.QtCore import QFile
import qtmax

UI_PATH = os.path.join(BASE_DIR, 'majestic_main.ui')

ui_dock_widget = None


def on_apply_filter_clicked():
    apply_filter_from_button_states(get_button_states())


class MajesticDockWidget(QtWidgets.QDockWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        loader = QUiLoader()
        ui_file = QFile(UI_PATH)
        ui_file.open(QFile.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()
        self.setWidget(self.ui)

        self.variant_buttons = []
        self.lod_buttons = []
        chk = self.findChild(QtWidgets.QCheckBox, 'chkEnableFilter')
        if chk:
            chk.toggled.connect(self.on_chk_enable_filter)

        self.populate_variant_buttons()
        self.setup_lod_buttons()
        self.on_chk_enable_filter(chk.isChecked() if chk else False)

    def populate_variant_buttons(self):
        group = self.findChild(QtWidgets.QGroupBox, 'groupBox_3')
        if not group:
            return
        layout = group.layout()
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        tags = []
        try:
            with open(GROUP_TAGS_PATH, 'r') as f:
                tags = json.load(f).get('groups', [])
        except Exception as e:
            print('[LODKit] failed to read nametags.json:', e)

        self.variant_buttons.clear()
        for idx, tag in enumerate(tags):
            btn = QtWidgets.QPushButton(tag)
            btn.setObjectName(f'btnVar_{tag}')
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.clicked.connect(self.on_any_button)
            row = idx // 4
            col = idx % 4
            layout.addWidget(btn, row, col)
            self.variant_buttons.append(btn)

    def setup_lod_buttons(self):
        for i in range(4):
            btn = self.findChild(QtWidgets.QPushButton, f'btnL{i}')
            if btn:
                btn.setCheckable(True)
                btn.setChecked(True)
                btn.clicked.connect(self.on_any_button)
                self.lod_buttons.append(btn)

    def on_chk_enable_filter(self, checked):
        frame = self.findChild(QtWidgets.QFrame, 'OBJframe')
        if frame:
            frame.setEnabled(checked)
        self.on_any_button()

    def on_any_button(self):
        apply_filter_from_button_states(self.get_button_states())

    def get_button_states(self):
        states = {}
        cb = self.findChild(QtWidgets.QCheckBox, 'chkEnableFilter')
        states['chkEnableFilter'] = cb.isChecked() if cb else False
        for i, btn in enumerate(self.lod_buttons):
            states[f'btnL{i}'] = btn.isChecked()
        for btn in self.variant_buttons:
            states[btn.objectName()] = btn.isChecked()
        return states

    def closeEvent(self, event):
        global ui_dock_widget
        ui_dock_widget = None
        event.accept()


def main():
    global ui_dock_widget

    if ui_dock_widget:
        try:
            ui_dock_widget.close()
        except Exception:
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
