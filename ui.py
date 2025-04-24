from PyQt5 import QtWidgets, QtCore, QtGui
import sys
import os

# Сопоставление Qt keycode → pynput vk для букв и цифр (macOS)
def qtkey_to_pynput_vk(qt_vk):
    # Буквы (A=0x41=65, ... Z=0x5A=90), pynput vk: A=0, B=11, C=8, D=2, E=14, F=3, G=5, H=4, I=34, J=38, K=40, L=37, M=46, N=45, O=31, P=35, Q=12, R=15, S=1, T=17, U=32, V=9, W=13, X=7, Y=16, Z=6
    qt_to_pynput = {
        65: 0, 66: 11, 67: 8, 68: 2, 69: 14, 70: 3, 71: 5, 72: 4, 73: 34, 74: 38, 75: 40, 76: 37, 77: 46, 78: 45, 79: 31, 80: 35, 81: 12, 82: 15, 83: 1, 84: 17, 85: 32, 86: 9, 87: 13, 88: 7, 89: 16, 90: 6,
        48: 29, 49: 18, 50: 19, 51: 20, 52: 21, 53: 23, 54: 22, 55: 26, 56: 28, 57: 25 # 0-9
    }
    return qt_to_pynput.get(qt_vk, qt_vk)

def get_applications():
    apps = set()
    app_dirs = ['/Applications', os.path.expanduser('~/Applications')]
    for app_dir in app_dirs:
        if os.path.exists(app_dir):
            for name in os.listdir(app_dir):
                if name.endswith('.app'):
                    apps.add(name[:-4])
    return sorted(apps)

class HotkeyInput(QtWidgets.QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText('Нажмите комбинацию...')
        self._mods = set()
        self._vk = None
        self._combo_str = ''
        self.setReadOnly(True)

    def keyPressEvent(self, event):
        mods = set()
        qt_mods = event.modifiers()
        if qt_mods & QtCore.Qt.ControlModifier:
            mods.add('Ctrl')
        if qt_mods & QtCore.Qt.AltModifier:
            mods.add('Alt')
        if qt_mods & QtCore.Qt.ShiftModifier:
            mods.add('Shift')
        if qt_mods & QtCore.Qt.MetaModifier:
            mods.add('Cmd')
        qt_vk = event.key()
        vk = qtkey_to_pynput_vk(qt_vk)
        # Для отображения
        key_map = {
            QtCore.Qt.Key_Return: 'Enter',
            QtCore.Qt.Key_Enter: 'Enter',
            QtCore.Qt.Key_Tab: 'Tab',
            QtCore.Qt.Key_Escape: 'Esc',
            QtCore.Qt.Key_Space: 'Space',
            QtCore.Qt.Key_Backspace: 'Backspace',
            QtCore.Qt.Key_Delete: 'Del',
            QtCore.Qt.Key_Left: 'Left',
            QtCore.Qt.Key_Right: 'Right',
            QtCore.Qt.Key_Up: 'Up',
            QtCore.Qt.Key_Down: 'Down',
        }
        if qt_vk in key_map:
            key_name = key_map[qt_vk]
        elif QtCore.Qt.Key_0 <= qt_vk <= QtCore.Qt.Key_9:
            key_name = f'{chr(qt_vk)}'
        elif QtCore.Qt.Key_A <= qt_vk <= QtCore.Qt.Key_Z:
            key_name = f'{chr(qt_vk)}'
        else:
            key_name = f'VK_{qt_vk}'
        mods_disp = ' + '.join(sorted(mods))
        self._mods = mods
        self._vk = vk
        self._combo_str = (mods_disp + (' + ' if mods_disp else '') + key_name).strip()
        self.setText(self._combo_str)

    def get_combo(self):
        return {'mods': sorted(self._mods), 'vk': self._vk, 'disp': self._combo_str}

class SettingsWindow(QtWidgets.QWidget):
    def __init__(self, load_hotkeys, save_hotkeys):
        super().__init__()
        self.setWindowTitle('HotkeyMaster — Настройки')
        self.load_hotkeys = load_hotkeys
        self.save_hotkeys = save_hotkeys
        layout = QtWidgets.QVBoxLayout()
        label = QtWidgets.QLabel('Настройки хоткеев')
        self.hotkey_list = QtWidgets.QListWidget()
        for hk in self.load_hotkeys():
            disp = hk.get('combo', {}).get('disp') if isinstance(hk.get('combo'), dict) else hk.get('combo', '')
            scope = hk.get('scope', 'global')
            app = hk.get('app', '')
            scope_disp = 'Глобальный' if scope == 'global' else f'Только для: {app}'
            self.hotkey_list.addItem(f"{disp} — {hk.get('action', '')} [{scope_disp}]")
        add_btn = QtWidgets.QPushButton('Добавить хоткей')
        del_btn = QtWidgets.QPushButton('Удалить выбранный')
        close_btn = QtWidgets.QPushButton('Закрыть')
        layout.addWidget(label)
        layout.addWidget(self.hotkey_list)
        layout.addWidget(add_btn)
        layout.addWidget(del_btn)
        layout.addWidget(close_btn)
        self.setLayout(layout)
        add_btn.clicked.connect(self.on_add)
        del_btn.clicked.connect(self.on_del)
        close_btn.clicked.connect(self.close)

    def on_add(self):
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle('Добавить хоткей')
        vbox = QtWidgets.QVBoxLayout()
        hotkey_input = HotkeyInput()
        vbox.addWidget(QtWidgets.QLabel('Комбинация:'))
        vbox.addWidget(hotkey_input)
        # Выбор типа действия
        action_type = QtWidgets.QComboBox()
        action_type.addItems(['Открыть сайт', 'Запустить программу/команду'])
        vbox.addWidget(QtWidgets.QLabel('Тип действия:'))
        vbox.addWidget(action_type)
        action_input = QtWidgets.QLineEdit()
        vbox.addWidget(QtWidgets.QLabel('URL или команда:'))
        vbox.addWidget(action_input)
        # Выбор области действия
        scope_type = QtWidgets.QComboBox()
        scope_type.addItems(['Глобальный', 'Только для приложения'])
        vbox.addWidget(QtWidgets.QLabel('Где работает хоткей:'))
        vbox.addWidget(scope_type)
        app_combo = QtWidgets.QComboBox()
        app_combo.addItems([''] + get_applications())
        app_combo.setEnabled(False)
        vbox.addWidget(app_combo)
        def on_scope_change(idx):
            app_combo.setEnabled(idx == 1)
        scope_type.currentIndexChanged.connect(on_scope_change)
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        vbox.addWidget(btns)
        dlg.setLayout(vbox)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            combo = hotkey_input.get_combo()
            action_val = action_input.text().strip()
            action = ''
            if action_type.currentIndex() == 0:
                # Только open, без run!
                action = f'open {action_val}'
            else:
                action = f'run {action_val}'
            scope = 'global' if scope_type.currentIndex() == 0 else 'app'
            app = app_combo.currentText() if scope == 'app' else ''
            if combo and action:
                hotkeys = self.load_hotkeys()
                hotkeys.append({'combo': combo, 'action': action, 'scope': scope, 'app': app})
                self.save_hotkeys(hotkeys)
                scope_disp = 'Глобальный' if scope == 'global' else f'Только для: {app}'
                self.hotkey_list.addItem(f"{combo['disp']} — {action} [{scope_disp}]")
                try:
                    import main
                    main.register_hotkeys()
                except Exception as e:
                    print(f'Ошибка перерегистрации хоткеев: {e}')

    def on_del(self):
        row = self.hotkey_list.currentRow()
        if row >= 0:
            hotkeys = self.load_hotkeys()
            if row < len(hotkeys):
                del hotkeys[row]
                self.save_hotkeys(hotkeys)
                self.hotkey_list.takeItem(row)
                # Перерегистрируем хоткеи сразу после удаления
                try:
                    import main
                    main.register_hotkeys()
                except Exception as e:
                    print(f'Ошибка перерегистрации хоткеев: {e}')

def show_settings_window(load_hotkeys, save_hotkeys):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    win = SettingsWindow(load_hotkeys, save_hotkeys)
    win.setWindowModality(QtCore.Qt.ApplicationModal)
    win.show()
    app.exec_()
