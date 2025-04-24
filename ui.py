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
        # self.setPlaceholderText('Нажмите комбинацию...')  # убрано, чтобы не мешал интерфейсу
        self._mods = set()
        self._vk = None
        self._combo_str = ''
        self.setReadOnly(True)

    def keyPressEvent(self, event):
        mods = set()
        qt_mods = event.modifiers()
        # Исправление для macOS: меняем местами Cmd и Ctrl
        if sys.platform == "darwin":
            if qt_mods & QtCore.Qt.ControlModifier:
                mods.add('Cmd')
            if qt_mods & QtCore.Qt.MetaModifier:
                mods.add('Ctrl')
        else:
            if qt_mods & QtCore.Qt.ControlModifier:
                mods.add('Ctrl')
            if qt_mods & QtCore.Qt.MetaModifier:
                mods.add('Cmd')
        if qt_mods & QtCore.Qt.AltModifier:
            mods.add('Alt')
        if qt_mods & QtCore.Qt.ShiftModifier:
            mods.add('Shift')
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
        self.resize(700, 400)
        main_layout = QtWidgets.QHBoxLayout()
        # Слева — выбор типа хоткеев
        self.type_list = QtWidgets.QListWidget()
        self.type_list.addItems(['Клавиатура', 'Трекпад'])
        # Справа — список хоткеев выбранного типа
        self.hotkey_list = QtWidgets.QListWidget()
        # --- Компактный layout: только три колонки ---
        self.type_list.setFixedWidth(140)
        self.hotkey_list.setMinimumWidth(320)
        self.hotkey_list.setWordWrap(True)
        self.details_scroll = QtWidgets.QScrollArea()
        self.details_scroll.setWidgetResizable(True)
        self.details_scroll.setMinimumWidth(340)
        main_layout.addWidget(self.type_list)
        main_layout.addWidget(self.hotkey_list)
        main_layout.addWidget(self.details_scroll)
        # Кнопки внизу
        btn_layout = QtWidgets.QHBoxLayout()
        self.add_btn = QtWidgets.QPushButton('Добавить')
        self.del_btn = QtWidgets.QPushButton('Удалить')
        self.close_btn = QtWidgets.QPushButton('Закрыть')
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.del_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.close_btn)
        # Весь layout
        vbox = QtWidgets.QVBoxLayout()
        vbox.addLayout(main_layout)
        vbox.addLayout(btn_layout)
        self.setLayout(vbox)
        # Сигналы
        self.type_list.currentRowChanged.connect(self.update_hotkey_list)
        self.add_btn.clicked.connect(self.on_add)
        self.del_btn.clicked.connect(self.on_del)
        self.close_btn.clicked.connect(self.close)
        # Инициализация
        self.type_list.setCurrentRow(0)
        self.update_hotkey_list(0)

    def update_hotkey_list(self, idx):
        self.hotkey_list.clear()
        hotkeys = self.load_hotkeys()
        if idx == 0:
            filtered = [hk for hk in hotkeys if hk.get('type', 'keyboard') == 'keyboard']
        else:
            filtered = [hk for hk in hotkeys if hk.get('type') == 'trackpad']
        self._filtered = filtered
        for hk in filtered:
            disp = hk.get('combo', {}).get('disp') if hk.get('type', 'keyboard') == 'keyboard' else hk.get('gesture', '')
            action = hk.get('action', '')
            scope = hk.get('scope', 'global')
            app = hk.get('app', '')
            scope_disp = 'Глобальный' if scope == 'global' else f'Только для: {app}'
            text = f"{disp}\n{action}\n{scope_disp}"
            item = QtWidgets.QListWidgetItem(text)
            item.setSizeHint(QtCore.QSize(item.sizeHint().width(), 48))
            self.hotkey_list.addItem(item)
        # Показываем настройки первого хоткея, если есть
        if self.hotkey_list.count() > 0:
            self.hotkey_list.setCurrentRow(0)
        else:
            self.show_hotkey_details(-1)
        # Важно: сигнал currentRowChanged должен быть подключён только один раз
        try:
            self.hotkey_list.currentRowChanged.disconnect()
        except Exception:
            pass
        self.hotkey_list.currentRowChanged.connect(self.show_hotkey_details)
        # Показываем настройки для выбранного (или первого) хоткея
        self.show_hotkey_details(self.hotkey_list.currentRow())

    def show_hotkey_details(self, row):
        # Удаляем старый виджет настроек, если был
        if hasattr(self, '_details_widget') and self._details_widget:
            self.details_scroll.takeWidget()
            self._details_widget.deleteLater()
            self._details_widget = None
        if row < 0 or row >= len(self._filtered):
            self.details_scroll.takeWidget()
            return
        hk = self._filtered[row]
        details = QtWidgets.QWidget()
        outer_vbox = QtWidgets.QVBoxLayout(details)
        group = QtWidgets.QGroupBox('Параметры')
        grid = QtWidgets.QGridLayout()
        row_idx = 0
        # --- Редактируемые поля ---
        if hk.get('type', 'keyboard') == 'keyboard':
            combo_input = HotkeyInput(details)
            combo_input.setText(hk.get('combo', {}).get('disp', ''))
            combo_input._mods = set(hk.get('combo', {}).get('mods', []))
            combo_input._vk = hk.get('combo', {}).get('vk')
            combo_input.setFixedWidth(180)
            grid.addWidget(QtWidgets.QLabel('Комбинация:'), row_idx, 0)
            grid.addWidget(combo_input, row_idx, 1)
            row_idx += 1
        else:
            gesture_combo = QtWidgets.QComboBox(details)
            gesture_combo.addItems([
                'Тап одним пальцем',
                'Тап двумя пальцами',
                'Тап тремя пальцами',
                'Тап четырьмя пальцами',
            ])
            if hk.get('gesture'):
                idx = gesture_combo.findText(hk.get('gesture'))
                if idx >= 0:
                    gesture_combo.setCurrentIndex(idx)
            grid.addWidget(QtWidgets.QLabel('Жест:'), row_idx, 0)
            grid.addWidget(gesture_combo, row_idx, 1)
            row_idx += 1
            scope_type = QtWidgets.QComboBox(details)
            scope_type.addItems(['Глобальный', 'Только для приложения'])
            scope_type.setCurrentIndex(0 if hk.get('scope', 'global') == 'global' else 1)
            grid.addWidget(QtWidgets.QLabel('Где работает жест:'), row_idx, 0)
            grid.addWidget(scope_type, row_idx, 1)
            row_idx += 1
            app_combo = QtWidgets.QComboBox(details)
            app_combo.addItems([''] + get_applications())
            app_combo.setEnabled(scope_type.currentIndex() == 1)
            if hk.get('app'):
                idx = app_combo.findText(hk.get('app'))
                if idx >= 0:
                    app_combo.setCurrentIndex(idx)
            grid.addWidget(QtWidgets.QLabel('Приложение:'), row_idx, 0)
            grid.addWidget(app_combo, row_idx, 1)
            row_idx += 1
            def on_scope_change(idx):
                app_combo.setEnabled(idx == 1)
            scope_type.currentIndexChanged.connect(on_scope_change)
        action_type = QtWidgets.QComboBox(details)
        action_type.addItems(['Открыть сайт', 'Запустить программу/команду', 'Нажать хоткей'])
        is_open = hk.get('action', '').startswith('open ')
        is_run = hk.get('action', '').startswith('run ')
        is_hotkey = hk.get('action', '').startswith('hotkey:')
        if is_open:
            action_type.setCurrentIndex(0)
        elif is_run:
            action_type.setCurrentIndex(1)
        else:
            action_type.setCurrentIndex(2)
        grid.addWidget(QtWidgets.QLabel('Тип действия:'), row_idx, 0)
        grid.addWidget(action_type, row_idx, 1)
        row_idx += 1
        action_input = QtWidgets.QLineEdit(details)
        hotkey_input = HotkeyInput(details)
        if is_open:
            action_input.setText(hk.get('action', '')[5:].strip())
        elif is_run:
            action_input.setText(hk.get('action', '')[4:].strip())
        if is_hotkey:
            import json
            try:
                combo = json.loads(hk.get('action', '')[7:])
                hotkey_input.setText(combo.get('disp', ''))
                hotkey_input._mods = set(combo.get('mods', []))
                hotkey_input._vk = combo.get('vk')
            except Exception:
                pass
        def set_action_field(idx):
            # Скрываем/показываем нужные поля
            action_input.setVisible(idx in (0, 1))
            hotkey_input.setVisible(idx == 2)
            if idx in (0, 1):
                grid.addWidget(QtWidgets.QLabel('URL или команда:'), row_idx, 0)
                grid.addWidget(action_input, row_idx, 1)
            elif idx == 2:
                grid.addWidget(QtWidgets.QLabel('Хоткей:'), row_idx, 0)
                grid.addWidget(hotkey_input, row_idx, 1)
        set_action_field(action_type.currentIndex())
        action_type.currentIndexChanged.connect(set_action_field)
        def save_changes():
            hotkeys = self.load_hotkeys()
            for i, h in enumerate(hotkeys):
                if h == hk:
                    if hk.get('type', 'keyboard') == 'keyboard':
                        combo = combo_input.get_combo()
                        gesture = ''
                        scope = 'global'
                        app = ''
                    else:
                        combo = None
                        gesture = gesture_combo.currentText()
                        scope = 'global' if scope_type.currentIndex() == 0 else 'app'
                        app = app_combo.currentText() if scope == 'app' else ''
                    if action_type.currentIndex() == 0:
                        action = f'open {action_input.text().strip()}'
                    elif action_type.currentIndex() == 1:
                        action = f'run {action_input.text().strip()}'
                    else:
                        import json
                        combo_val = hotkey_input.get_combo()
                        action = 'hotkey:' + json.dumps(combo_val, ensure_ascii=False)
                    hotkeys[i] = {
                        'type': hk.get('type'),
                        'combo': combo,
                        'gesture': gesture,
                        'action': action,
                        'scope': scope,
                        'app': app
                    }
                    break
            self.save_hotkeys(hotkeys)
            try:
                import main
                main.register_hotkeys()
            except Exception as e:
                print(f'Ошибка перерегистрации хоткеев: {e}')
            self.update_hotkey_list(self.type_list.currentRow())
            self.hotkey_list.setCurrentRow(row)
        if hk.get('type', 'keyboard') == 'keyboard':
            combo_input.textChanged.connect(save_changes)
        else:
            gesture_combo.currentIndexChanged.connect(save_changes)
            scope_type.currentIndexChanged.connect(save_changes)
            app_combo.currentIndexChanged.connect(save_changes)
        action_type.currentIndexChanged.connect(save_changes)
        action_input.textChanged.connect(save_changes)
        hotkey_input.textChanged.connect(save_changes)
        group.setLayout(grid)
        outer_vbox.addWidget(group)
        outer_vbox.addStretch()
        details.setLayout(outer_vbox)
        self._details_widget = details
        self.details_scroll.setWidget(details)

    def on_add(self):
        idx = self.type_list.currentRow()
        if idx == 0:
            self._add_keyboard_hotkey()
        else:
            self._add_trackpad_hotkey()
        self.update_hotkey_list(idx)

    def on_del(self):
        idx = self.type_list.currentRow()
        row = self.hotkey_list.currentRow()
        if row < 0 or row >= len(self._filtered):
            return
        hotkeys = self.load_hotkeys()
        # Удаляем по совпадению объекта
        for i, h in enumerate(hotkeys):
            if h == self._filtered[row]:
                del hotkeys[i]
                break
        self.save_hotkeys(hotkeys)
        self.update_hotkey_list(idx)
        try:
            import main
            main.register_hotkeys()
        except Exception as e:
            print(f'Ошибка перерегистрации хоткеев: {e}')

    def _add_keyboard_hotkey(self):
        # ...переиспользовать старый on_add для клавиатуры...
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle('Добавить клавиатурный хоткей')
        vbox = QtWidgets.QVBoxLayout()
        hotkey_input = HotkeyInput()
        vbox.addWidget(QtWidgets.QLabel('Комбинация:'))
        vbox.addWidget(hotkey_input)
        action_type = QtWidgets.QComboBox()
        action_type.addItems(['Открыть сайт', 'Запустить программу/команду'])
        vbox.addWidget(QtWidgets.QLabel('Тип действия:'))
        vbox.addWidget(action_type)
        action_input = QtWidgets.QLineEdit()
        vbox.addWidget(QtWidgets.QLabel('URL или команда:'))
        vbox.addWidget(action_input)
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
            action = f'open {action_val}' if action_type.currentIndex() == 0 else f'run {action_val}'
            scope = 'global' if scope_type.currentIndex() == 0 else 'app'
            app = app_combo.currentText() if scope == 'app' else ''
            if combo and action:
                hotkeys = self.load_hotkeys()
                hotkeys.append({'type': 'keyboard', 'combo': combo, 'gesture': '', 'action': action, 'scope': scope, 'app': app})
                self.save_hotkeys(hotkeys)
                try:
                    import main
                    main.register_hotkeys()
                except Exception as e:
                    print(f'Ошибка перерегистрации хоткеев: {e}')

    def _add_trackpad_hotkey(self):
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle('Добавить трекпад-жест')
        vbox = QtWidgets.QVBoxLayout()
        gesture_combo = QtWidgets.QComboBox()
        gesture_combo.addItems([
            'Тап одним пальцем',
            'Тап двумя пальцами',
            'Тап тремя пальцами',
            'Тап четырьмя пальцами',
        ])
        vbox.addWidget(QtWidgets.QLabel('Жест:'))
        vbox.addWidget(gesture_combo)
        action_type = QtWidgets.QComboBox()
        action_type.addItems(['Открыть сайт', 'Запустить программу/команду', 'Нажать хоткей'])
        vbox.addWidget(QtWidgets.QLabel('Тип действия:'))
        vbox.addWidget(action_type)
        action_input = QtWidgets.QLineEdit()
        vbox.addWidget(QtWidgets.QLabel('URL или команда:'))
        vbox.addWidget(action_input)
        hotkey_input = HotkeyInput()
        vbox.addWidget(QtWidgets.QLabel('Хоткей:'))
        vbox.addWidget(hotkey_input)
        hotkey_input.setVisible(False)
        def set_action_field(idx):
            action_input.setVisible(idx in (0, 1))
            hotkey_input.setVisible(idx == 2)
        set_action_field(action_type.currentIndex())
        action_type.currentIndexChanged.connect(set_action_field)
        scope_type = QtWidgets.QComboBox()
        scope_type.addItems(['Глобальный', 'Только для приложения'])
        vbox.addWidget(QtWidgets.QLabel('Где работает жест:'))
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
            gesture = gesture_combo.currentText()
            action_val = action_input.text().strip()
            if action_type.currentIndex() == 0:
                action = f'open {action_val}'
            elif action_type.currentIndex() == 1:
                action = f'run {action_val}'
            else:
                import json
                combo_val = hotkey_input.get_combo()
                action = 'hotkey:' + json.dumps(combo_val, ensure_ascii=False)
            scope = 'global' if scope_type.currentIndex() == 0 else 'app'
            app = app_combo.currentText() if scope == 'app' else ''
            if gesture and action:
                hotkeys = self.load_hotkeys()
                hotkeys.append({'type': 'trackpad', 'combo': None, 'gesture': gesture, 'action': action, 'scope': scope, 'app': app})
                self.save_hotkeys(hotkeys)
                try:
                    import main
                    main.register_hotkeys()
                except Exception as e:
                    print(f'Ошибка перерегистрации хоткеев: {e}')

    def _edit_keyboard_hotkey(self, hk):
        # ...можно переиспользовать on_edit для клавиатуры...
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle('Редактировать клавиатурный хоткей')
        vbox = QtWidgets.QVBoxLayout()
        hotkey_input = HotkeyInput()
        if isinstance(hk.get('combo'), dict):
            hotkey_input.setText(hk['combo'].get('disp', ''))
            hotkey_input._mods = set(hk['combo'].get('mods', []))
            hotkey_input._vk = hk['combo'].get('vk')
        vbox.addWidget(QtWidgets.QLabel('Комбинация:'))
        vbox.addWidget(hotkey_input)
        action_type = QtWidgets.QComboBox()
        action_type.addItems(['Открыть сайт', 'Запустить программу/команду'])
        is_open = hk.get('action', '').startswith('open ')
        is_run = hk.get('action', '').startswith('run ')
        is_hotkey = hk.get('action', '').startswith('hotkey:')
        if is_open:
            action_type.setCurrentIndex(0)
        elif is_run:
            action_type.setCurrentIndex(1)
        else:
            action_type.setCurrentIndex(2)
        vbox.addWidget(QtWidgets.QLabel('Тип действия:'))
        vbox.addWidget(action_type)
        action_input = QtWidgets.QLineEdit()
        if is_open:
            action_input.setText(hk.get('action', '')[5:].strip())
        elif is_run:
            action_input.setText(hk.get('action', '')[4:].strip())
        vbox.addWidget(QtWidgets.QLabel('URL или команда:'))
        vbox.addWidget(action_input)
        hotkey_input = HotkeyInput()
        if is_hotkey:
            import json
            try:
                combo = json.loads(hk.get('action', '')[7:])
                hotkey_input.setText(combo.get('disp', ''))
                hotkey_input._mods = set(combo.get('mods', []))
                hotkey_input._vk = combo.get('vk')
            except Exception:
                pass
        vbox.addWidget(QtWidgets.QLabel('Хоткей:'))
        vbox.addWidget(hotkey_input)
        def set_action_field(idx):
            action_input.setVisible(idx in (0, 1))
            hotkey_input.setVisible(idx == 2)
        set_action_field(action_type.currentIndex())
        action_type.currentIndexChanged.connect(set_action_field)
        scope_type = QtWidgets.QComboBox()
        scope_type.addItems(['Глобальный', 'Только для приложения'])
        scope_type.setCurrentIndex(0 if hk.get('scope', 'global') == 'global' else 1)
        vbox.addWidget(QtWidgets.QLabel('Где работает хоткей:'))
        vbox.addWidget(scope_type)
        app_combo = QtWidgets.QComboBox()
        app_combo.addItems([''] + get_applications())
        app_combo.setEnabled(scope_type.currentIndex() == 1)
        if hk.get('app'):
            idx = app_combo.findText(hk.get('app'))
            if idx >= 0:
                app_combo.setCurrentIndex(idx)
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
            action = f'open {action_val}' if action_type.currentIndex() == 0 else f'run {action_val}'
            scope = 'global' if scope_type.currentIndex() == 0 else 'app'
            app = app_combo.currentText() if scope == 'app' else ''
            if combo and action:
                # Найти и заменить в hotkeys.json
                hotkeys = self.load_hotkeys()
                for i, h in enumerate(hotkeys):
                    if h == hk:
                        hotkeys[i] = {'type': 'keyboard', 'combo': combo, 'gesture': '', 'action': action, 'scope': scope, 'app': app}
                        break
                self.save_hotkeys(hotkeys)
                try:
                    import main
                    main.register_hotkeys()
                except Exception as e:
                    print(f'Ошибка перерегистрации хоткеев: {e}')

    def _edit_trackpad_hotkey(self, hk):
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle('Редактировать трекпад-жест')
        vbox = QtWidgets.QVBoxLayout()
        gesture_combo = QtWidgets.QComboBox()
        gesture_combo.addItems([
            'Тап одним пальцем',
            'Тап двумя пальцами',
            'Тап тремя пальцами',
            'Тап четырьмя пальцами',
        ])
        if hk.get('gesture'):
            idx = gesture_combo.findText(hk.get('gesture'))
            if idx >= 0:
                gesture_combo.setCurrentIndex(idx)
        vbox.addWidget(QtWidgets.QLabel('Жест:'))
        vbox.addWidget(gesture_combo)
        action_type = QtWidgets.QComboBox()
        action_type.addItems(['Открыть сайт', 'Запустить программу/команду', 'Нажать хоткей'])
        is_open = hk.get('action', '').startswith('open ')
        is_run = hk.get('action', '').startswith('run ')
        is_hotkey = hk.get('action', '').startswith('hotkey:')
        if is_open:
            action_type.setCurrentIndex(0)
        elif is_run:
            action_type.setCurrentIndex(1)
        else:
            action_type.setCurrentIndex(2)
        vbox.addWidget(QtWidgets.QLabel('Тип действия:'))
        vbox.addWidget(action_type)
        action_input = QtWidgets.QLineEdit()
        if is_open:
            action_input.setText(hk.get('action', '')[5:].strip())
        elif is_run:
            action_input.setText(hk.get('action', '')[4:].strip())
        vbox.addWidget(QtWidgets.QLabel('URL или команда:'))
        vbox.addWidget(action_input)
        hotkey_input = HotkeyInput()
        if is_hotkey:
            import json
            try:
                combo = json.loads(hk.get('action', '')[7:])
                hotkey_input.setText(combo.get('disp', ''))
                hotkey_input._mods = set(combo.get('mods', []))
                hotkey_input._vk = combo.get('vk')
            except Exception:
                pass
        vbox.addWidget(QtWidgets.QLabel('Хоткей:'))
        vbox.addWidget(hotkey_input)
        def set_action_field(idx):
            action_input.setVisible(idx in (0, 1))
            hotkey_input.setVisible(idx == 2)
        set_action_field(action_type.currentIndex())
        action_type.currentIndexChanged.connect(set_action_field)
        scope_type = QtWidgets.QComboBox()
        scope_type.addItems(['Глобальный', 'Только для приложения'])
        scope_type.setCurrentIndex(0 if hk.get('scope', 'global') == 'global' else 1)
        vbox.addWidget(QtWidgets.QLabel('Где работает жест:'))
        vbox.addWidget(scope_type)
        app_combo = QtWidgets.QComboBox()
        app_combo.addItems([''] + get_applications())
        app_combo.setEnabled(scope_type.currentIndex() == 1)
        if hk.get('app'):
            idx = app_combo.findText(hk.get('app'))
            if idx >= 0:
                app_combo.setCurrentIndex(idx)
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
            gesture = gesture_combo.currentText()
            action_val = action_input.text().strip()
            if action_type.currentIndex() == 0:
                action = f'open {action_val}'
            elif action_type.currentIndex() == 1:
                action = f'run {action_val}'
            else:
                import json
                combo_val = hotkey_input.get_combo()
                action = 'hotkey:' + json.dumps(combo_val, ensure_ascii=False)
            scope = 'global' if scope_type.currentIndex() == 0 else 'app'
            app = app_combo.currentText() if scope == 'app' else ''
            if gesture and action:
                # Найти и заменить в hotkeys.json
                hotkeys = self.load_hotkeys()
                for i, h in enumerate(hotkeys):
                    if h == hk:
                        hotkeys[i] = {'type': 'trackpad', 'combo': None, 'gesture': gesture, 'action': action, 'scope': scope, 'app': app}
                        break
                self.save_hotkeys(hotkeys)
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
