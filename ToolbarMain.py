import os
import sys
import json
import importlib

BASE_DIR = os.path.dirname(__file__)
sys.path.insert(0, BASE_DIR)

import lodkitfilter
importlib.reload(lodkitfilter)

from lodkitfilter import (
    apply_filter_from_button_states,
    enable_filter,
    disable_filter,
    make_layers,
    GROUP_TAGS_PATH,
)

try:
    from PySide6 import QtWidgets, QtCore
    from PySide6.QtUiTools import QUiLoader
    from PySide6.QtCore import QFile
except ImportError:
    from PySide2 import QtWidgets, QtCore
    from PySide2.QtUiTools import QUiLoader
    from PySide2.QtCore import QFile
    
import qtmax


UI_PATH = os.path.join(BASE_DIR, 'majestic_main.ui')

ui_dock_widget = None


class MajesticDockWidget(QtWidgets.QDockWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        loader = QUiLoader()
        ui_file = QFile(UI_PATH)
        ui_file.open(QFile.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()
        self.setWidget(self.ui)

        chk = self.findChild(QtWidgets.QCheckBox, 'chkEnableFilter')
        if chk:
            chk.setChecked(False)
            chk.toggled.connect(self.on_chk_enable_filter)
            frame = self.findChild(QtWidgets.QFrame, 'OBJframe')
            if frame:
                frame.setEnabled(False)

        self.setup_lod_buttons()

        btn_layers = self.findChild(QtWidgets.QPushButton, 'btnMakeLayers')
        if btn_layers:
            btn_layers.clicked.connect(self.on_make_layers)

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

        for idx, tag in enumerate(tags):
            btn = QtWidgets.QPushButton(tag)
            btn.setObjectName(f'btnVar_{tag}')
            btn.setCheckable(True)
            btn.setChecked(False)
            btn.clicked.connect(self.on_any_button)
            row = idx // 2
            col = idx % 2
            layout.addWidget(btn, row, col)

    def clear_variant_buttons(self):
        group = self.findChild(QtWidgets.QGroupBox, 'groupBox_3')
        if not group:
            return
        layout = group.layout()
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def setup_lod_buttons(self):
        self.lod_group = QtWidgets.QButtonGroup(self)
        self.lod_group.setExclusive(True)
        for i in range(4):
            btn = self.findChild(QtWidgets.QPushButton, f'btnL{i}')
            if btn:
                btn.setCheckable(True)
                self.lod_group.addButton(btn)
                btn.setChecked(i == 0)
                btn.clicked.connect(self.on_any_button)

    def on_chk_enable_filter(self, checked):
        frame = self.findChild(QtWidgets.QFrame, 'OBJframe')
        if frame:
            frame.setEnabled(checked)
        if checked:
            enable_filter()
            self.populate_variant_buttons()
        else:
            self.clear_variant_buttons()
            disable_filter()
        states = self.collect_states()
        apply_filter_from_button_states(states)

    def on_any_button(self):
        states = self.collect_states()
        apply_filter_from_button_states(states)

    def on_make_layers(self):
        make_layers()

    def collect_states(self):
        states = {}
        cb = self.findChild(QtWidgets.QCheckBox, 'chkEnableFilter')
        states['chkEnableFilter'] = cb.isChecked() if cb else False
        for i in range(4):
            btn = self.findChild(QtWidgets.QPushButton, f'btnL{i}')
            if btn:
                states[f'btnL{i}'] = btn.isChecked()
        for btn in self.findChildren(QtWidgets.QPushButton):
            name = btn.objectName()
            if name.startswith('btnVar_'):
                states[name] = btn.isChecked()
        return states

    def closeEvent(self, event):
        global ui_dock_widget
        ui_dock_widget = None
        event.accept()




def main():
    """Launch the toolbar and run the auto-updater."""

    global ui_dock_widget

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


    if ui_dock_widget:
        try:
            ui_dock_widget.close()
        except Exception:
            pass

    parent = qtmax.GetQMaxMainWindow()
    ui_dock_widget = MajesticDockWidget(parent)
    ui_dock_widget.setFloating(True)
    ui_dock_widget.show()


if __name__ == '__main__':
    ui_dock_widget = None
    main()
