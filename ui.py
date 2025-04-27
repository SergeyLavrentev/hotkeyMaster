from PyQt5 import QtWidgets, QtCore, QtGui
import sys
import os
import threading
import Quartz
import subprocess
import json
import sip

# Сопоставление Qt keycode → pynput vk для букв и цифр (macOS)
def qtkey_to_pynput_vk(qt_vk):
    # Буквы A-Z
    qt_to_pynput = {
        65: 0, 66: 11, 67: 8, 68: 2, 69: 14, 70: 3, 71: 5, 72: 4, 73: 34, 74: 38, 75: 40, 76: 37, 77: 46, 78: 45, 79: 31, 80: 35, 81: 12, 82: 15, 83: 1, 84: 17, 85: 32, 86: 9, 87: 13, 88: 7, 89: 16, 90: 6,
        # Цифры 0-9
        48: 29, 49: 18, 50: 19, 51: 20, 52: 21, 53: 23, 54: 22, 55: 26, 56: 28, 57: 25,
        # F-клавиши (Qt -> macOS VK)
        QtCore.Qt.Key_F1: 122, QtCore.Qt.Key_F2: 120, QtCore.Qt.Key_F3: 99, QtCore.Qt.Key_F4: 118,
        QtCore.Qt.Key_F5: 96, QtCore.Qt.Key_F6: 97, QtCore.Qt.Key_F7: 98, QtCore.Qt.Key_F8: 100,
        QtCore.Qt.Key_F9: 101, QtCore.Qt.Key_F10: 109, QtCore.Qt.Key_F11: 103, QtCore.Qt.Key_F12: 111,
        # Добавим основные спец. клавиши, если они еще не покрыты
        QtCore.Qt.Key_Return: 36, QtCore.Qt.Key_Enter: 76, # Enter на основной и цифровой клавиатуре
        QtCore.Qt.Key_Tab: 48,
        QtCore.Qt.Key_Escape: 53,
        QtCore.Qt.Key_Space: 49,
        QtCore.Qt.Key_Backspace: 51,
        QtCore.Qt.Key_Delete: 117,
        QtCore.Qt.Key_Left: 123, QtCore.Qt.Key_Right: 124, QtCore.Qt.Key_Up: 126, QtCore.Qt.Key_Down: 125,
    }
    # --- ДОБАВЛЕНО: Fn-клавиши MacBook (яркость, звук, media) ---
    fn_keys = {
        QtCore.Qt.Key_MonBrightnessUp: 113,    # F14 (яркость +)
        QtCore.Qt.Key_MonBrightnessDown: 107,  # F15 (яркость -)
        QtCore.Qt.Key_KeyboardBrightnessUp: 145,   # F6 (подсветка клавиатуры +)
        QtCore.Qt.Key_KeyboardBrightnessDown: 144, # F5 (подсветка клавиатуры -)
        QtCore.Qt.Key_VolumeUp: 72,            # F12 (громкость +)
        QtCore.Qt.Key_VolumeDown: 73,          # F11 (громкость -)
        QtCore.Qt.Key_VolumeMute: 74,          # F10 (mute)
        QtCore.Qt.Key_MediaPlay: 16,           # F8 (play/pause)
        QtCore.Qt.Key_MediaNext: 17,           # F9 (next)
        QtCore.Qt.Key_MediaPrevious: 15,       # F7 (prev)
        # ...можно добавить другие Fn-клавиши по необходимости...
    }
    if qt_vk in fn_keys:
        return fn_keys[qt_vk]
    return qt_to_pynput.get(qt_vk)

def get_applications():
    apps = set()
    app_dirs = ['/Applications', os.path.expanduser('~/Applications')]
    for app_dir in app_dirs:
        if os.path.exists(app_dir):
            for name in os.listdir(app_dir):
                if name.endswith('.app'):
                    apps.add(name[:-4])
    return sorted(apps)

class GlobalHotkeyCapture:
    def __init__(self, callback):
        self.callback = callback
        self._stop_event = threading.Event()
        self._thread = None
        self._captured = None

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()

    def _run(self):
        MODS_MAP = {
            Quartz.kCGEventFlagMaskCommand: 'Cmd',
            Quartz.kCGEventFlagMaskShift: 'Shift',
            Quartz.kCGEventFlagMaskAlternate: 'Alt',
            Quartz.kCGEventFlagMaskControl: 'Ctrl',
        }
        def get_mods(flags):
            mods = set()
            for mask, name in MODS_MAP.items():
                if flags & mask:
                    mods.add(name)
            return mods
        def event_callback(proxy, type_, event, refcon):
            if type_ != Quartz.kCGEventKeyDown:
                return event
            vk = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
            flags = Quartz.CGEventGetFlags(event)
            mods = get_mods(flags)
            self._captured = (vk, mods)
            if self.callback:
                self.callback(vk, mods)
            self.stop()
            return None
        mask = Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
        tap = Quartz.CGEventTapCreate(
            Quartz.kCGHIDEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionDefault,
            mask,
            event_callback,
            None
        )
        if not tap:
            return
        run_loop_source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
        loop = Quartz.CFRunLoopGetCurrent()
        Quartz.CFRunLoopAddSource(loop, run_loop_source, Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(tap, True)
        while not self._stop_event.is_set():
            Quartz.CFRunLoopRunInMode(Quartz.kCFRunLoopDefaultMode, 0.1, False)
        Quartz.CFRunLoopRemoveSource(loop, run_loop_source, Quartz.kCFRunLoopCommonModes)
        Quartz.CFMachPortInvalidate(tap)

class HotkeyInput(QtWidgets.QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._prev_mods = set()
        self._prev_vk = None
        self._prev_combo_str = ''
        # self.setPlaceholderText('Нажмите комбинацию...')  # убрано, чтобы не мешал интерфейсу
        self._mods = set()
        self._vk = None
        self._combo_str = ''
        self.setReadOnly(True)

    def keyPressEvent(self, event):
        # Отмена ввода по Esc: восстанавливаем старую комбинацию
        if event.key() == QtCore.Qt.Key_Escape:
            self.setText(self._prev_combo_str)
            self._mods = set(self._prev_mods)
            self._vk = self._prev_vk
            self._combo_str = self._prev_combo_str
            # Останавливаем захват из subprocess
            if hasattr(self, '_capture_proc') and self._capture_proc:
                self._capture_proc.terminate()
                self._capture_proc = None
            return
        mods = set()
        qt_mods = event.modifiers()
        qt_vk = event.key()
        # --- определяем модификаторы ---
        if sys.platform == "darwin":
            if qt_mods & QtCore.Qt.ControlModifier: mods.add('Cmd')
            if qt_mods & QtCore.Qt.MetaModifier: mods.add('Ctrl')
        else:
            if qt_mods & QtCore.Qt.ControlModifier: mods.add('Ctrl')
            if qt_mods & QtCore.Qt.MetaModifier: mods.add('Cmd')
        if qt_mods & QtCore.Qt.AltModifier: mods.add('Alt')
        if qt_mods & QtCore.Qt.ShiftModifier: mods.add('Shift')
        fn_names = {
            QtCore.Qt.Key_MonBrightnessUp: 'Яркость +',
            QtCore.Qt.Key_MonBrightnessDown: 'Яркость -',
            QtCore.Qt.Key_KeyboardBrightnessUp: 'Подсветка клавиатуры +',
            QtCore.Qt.Key_KeyboardBrightnessDown: 'Подсветка клавиатуры -',
            QtCore.Qt.Key_VolumeUp: 'Громкость +',
            QtCore.Qt.Key_VolumeDown: 'Громкость -',
            QtCore.Qt.Key_VolumeMute: 'Mute',
            QtCore.Qt.Key_MediaPlay: 'Play/Pause',
            QtCore.Qt.Key_MediaNext: 'Next',
            QtCore.Qt.Key_MediaPrevious: 'Prev',
        }
        if qt_vk in fn_names:
            vk = qtkey_to_pynput_vk(qt_vk)
            mods_disp = ' + '.join(sorted(mods))
            key_name = fn_names[qt_vk]
            self._mods = mods
            self._vk = vk
            self._combo_str = (mods_disp + (' + ' if mods_disp else '') + key_name).strip()
            self.setText(self._combo_str)
            return
        # --- КОНЕЦ ДОБАВЛЕНИЯ ---

        modifier_keys = {
            QtCore.Qt.Key_Control, QtCore.Qt.Key_Shift, QtCore.Qt.Key_Alt,
            QtCore.Qt.Key_Meta, QtCore.Qt.Key_CapsLock,
            QtCore.Qt.Key_AltGr, QtCore.Qt.Key_Super_L, QtCore.Qt.Key_Super_R,
            QtCore.Qt.Key_Hyper_L, QtCore.Qt.Key_Hyper_R
        }

        # --- ИЗМЕНЕНИЕ: Игнорируем, если нажата только клавиша-модификатор ---
        if qt_vk in modifier_keys:
            if sys.platform == "darwin":
                if qt_mods & QtCore.Qt.ControlModifier: mods.add('Cmd')
                if qt_mods & QtCore.Qt.MetaModifier: mods.add('Ctrl')
            else:
                if qt_mods & QtCore.Qt.ControlModifier: mods.add('Ctrl')
                if qt_mods & QtCore.Qt.MetaModifier: mods.add('Cmd')
            if qt_mods & QtCore.Qt.AltModifier: mods.add('Alt')
            if qt_mods & QtCore.Qt.ShiftModifier: mods.add('Shift')
            self.setText(' + '.join(sorted(mods)) + ' + ...')
            self._mods = mods # Сохраняем модификаторы
            self._vk = None # Сбрасываем vk
            self._combo_str = '' # Сбрасываем строку
            return # Не обрабатываем дальше
        # --- КОНЕЦ ИЗМЕНЕНИЯ ---

        # Определяем модификаторы (как и раньше)
        if sys.platform == "darwin":
            if qt_mods & QtCore.Qt.ControlModifier: mods.add('Cmd')
            if qt_mods & QtCore.Qt.MetaModifier: mods.add('Ctrl')
        else:
            if qt_mods & QtCore.Qt.ControlModifier: mods.add('Ctrl')
            if qt_mods & QtCore.Qt.MetaModifier: mods.add('Cmd')
        if qt_mods & QtCore.Qt.AltModifier: mods.add('Alt')
        if qt_mods & QtCore.Qt.ShiftModifier: mods.add('Shift')

        # Получаем vk для pynput
        vk = qtkey_to_pynput_vk(qt_vk)

        # Если vk не найден (None), то комбинация невалидна
        if vk is None:
             self.setText("<Неподдерживаемая клавиша>")
             self._mods = mods # Сохраняем модификаторы
             self._vk = None    # Убедимся, что vk это None
             self._combo_str = '' # Сбрасываем строку
             return

        # Для отображения (как и раньше, но используем vk для F-клавиш)
        key_map = {
            QtCore.Qt.Key_Return: 'Enter', QtCore.Qt.Key_Enter: 'Enter',
            QtCore.Qt.Key_Tab: 'Tab', QtCore.Qt.Key_Escape: 'Esc',
            QtCore.Qt.Key_Space: 'Space', QtCore.Qt.Key_Backspace: 'Backspace',
            QtCore.Qt.Key_Delete: 'Del', QtCore.Qt.Key_Left: 'Left',
            QtCore.Qt.Key_Right: 'Right', QtCore.Qt.Key_Up: 'Up',
            QtCore.Qt.Key_Down: 'Down',
            QtCore.Qt.Key_F1: 'F1', QtCore.Qt.Key_F2: 'F2', QtCore.Qt.Key_F3: 'F3',
            QtCore.Qt.Key_F4: 'F4', QtCore.Qt.Key_F5: 'F5', QtCore.Qt.Key_F6: 'F6',
            QtCore.Qt.Key_F7: 'F7', QtCore.Qt.Key_F8: 'F8', QtCore.Qt.Key_F9: 'F9',
            QtCore.Qt.Key_F10: 'F10', QtCore.Qt.Key_F11: 'F11', QtCore.Qt.Key_F12: 'F12',
        }
        if qt_vk in key_map:
            key_name = key_map[qt_vk]
        elif QtCore.Qt.Key_0 <= qt_vk <= QtCore.Qt.Key_9:
            key_name = f'{chr(qt_vk)}'
        elif QtCore.Qt.Key_A <= qt_vk <= QtCore.Qt.Key_Z:
            key_name = f'{chr(qt_vk)}'
        else:
            # Попытка отобразить символ, иначе VK-код
            txt = event.text()
            if txt:
                key_name = txt.upper()
            else:
                key_name = f'VK_{vk}' # Отображаем pynput vk

        mods_disp = ' + '.join(sorted(mods))
        self._mods = mods
        self._vk = vk # Сохраняем pynput vk
        self._combo_str = (mods_disp + (' + ' if mods_disp else '') + key_name).strip()
        self.setText(self._combo_str)

    def get_combo(self):
        # Всегда возвращаем словарь, но vk может быть None
        return {'mods': sorted(list(self._mods)), 'vk': self._vk, 'disp': self._combo_str}

    def focusInEvent(self, event):
        super().focusInEvent(event)
        # Сохраняем предыдущую комбинацию для отмены
        self._prev_mods = set(self._mods)
        self._prev_vk = self._vk
        self._prev_combo_str = self._combo_str
        self.setText('Нажмите любую клавишу...')
        self._capture_proc = subprocess.Popen([
            sys.executable, os.path.join(os.path.dirname(__file__), 'hotkey_capture_helper.py')
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self._wait_for_hotkey()
    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        if hasattr(self, '_capture_proc') and self._capture_proc:
            self._capture_proc.terminate()
            self._capture_proc = None
    def _wait_for_hotkey(self):
        if not hasattr(self, '_capture_proc') or self._capture_proc is None:
            return
        ret = self._capture_proc.poll()
        if ret is None:
            QtCore.QTimer.singleShot(50, self._wait_for_hotkey)
            return
        out, err = self._capture_proc.communicate()
        def update_ui():
            try:
                data = json.loads(out.decode('utf-8').strip())
                vk = data.get('vk')
                mods = set(data.get('mods', []))
                fn_names = {
                    122: 'F1', 120: 'F2', 99: 'F3', 118: 'F4', 96: 'F5', 97: 'F6', 98: 'F7', 100: 'F8', 101: 'F9', 109: 'F10', 103: 'F11', 111: 'F12',
                    113: 'Яркость +', 107: 'Яркость -', 145: 'Подсветка клавиатуры +', 144: 'Подсветка клавиатуры -',
                    72: 'Громкость +', 73: 'Громкость -', 74: 'Mute', 16: 'Play/Pause', 17: 'Next', 15: 'Prev',
                }
                # По возможности отображаем цифры и буквы
                digit_map = {29:'0',18:'1',19:'2',20:'3',21:'4',23:'5',22:'6',26:'7',28:'8',25:'9'}
                letter_map = {0:'A',11:'B',8:'C',2:'D',14:'E',3:'F',5:'G',4:'H',34:'I',38:'J',40:'K',37:'L',46:'M',45:'N',31:'O',35:'P',12:'Q',15:'R',1:'S',17:'T',32:'U',9:'V',13:'W',7:'X',16:'Y',6:'Z'}
                if vk in digit_map:
                    key_name = digit_map[vk]
                elif vk in letter_map:
                    key_name = letter_map[vk]
                else:
                    key_name = fn_names.get(vk, f'VK_{vk}')
                mods_disp = ' + '.join(sorted(mods))
                self._mods = mods
                self._vk = vk
                self._combo_str = (mods_disp + (' + ' if mods_disp else '') + key_name).strip()
                self.setText(self._combo_str)
            except Exception as e:
                self.setText('<Ошибка захвата хоткея>')
            self._capture_proc = None
        QtCore.QTimer.singleShot(0, update_ui)

class SettingsWindow(QtWidgets.QDialog):
    def __init__(self, load_hotkeys, save_hotkeys):
        super().__init__()
        self.setWindowTitle('HotkeyMaster — Настройки')
        self.load_hotkeys = load_hotkeys
        self.save_hotkeys = save_hotkeys
        self.resize(700, 500)
        main_layout = QtWidgets.QVBoxLayout()
        # --- Общие настройки ---
        self.general_group = QtWidgets.QGroupBox('Общие настройки')
        general_layout = QtWidgets.QVBoxLayout()
        self.autostart_cb = QtWidgets.QCheckBox('Автостарт при запуске macOS')
        general_layout.addWidget(self.autostart_cb)
        self.general_group.setLayout(general_layout)
        # ...existing code for type_list, hotkey_list, details_scroll...
        hbox = QtWidgets.QHBoxLayout()
        self.type_list = QtWidgets.QListWidget()
        self.type_list.addItems(['Клавиатура', 'Трекпад'])
        self.hotkey_list = QtWidgets.QListWidget()
        self.hotkey_list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.hotkey_list.setMinimumWidth(320)
        self.hotkey_list.setWordWrap(True)
        self.hotkey_list.setIconSize(QtCore.QSize(20, 20))
        self.details_scroll = QtWidgets.QScrollArea()
        self.details_scroll.setWidgetResizable(True)
        self.details_scroll.setMinimumWidth(340)
        hbox.addWidget(self.type_list)
        hbox.addWidget(self.hotkey_list)
        hbox.addWidget(self.details_scroll)
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
        main_layout.addWidget(self.general_group)
        main_layout.addLayout(hbox)
        main_layout.addLayout(btn_layout)
        self.setLayout(main_layout)
        # --- Загрузка и сохранение общих настроек ---
        self.load_general_settings()
        self.autostart_cb.stateChanged.connect(self.save_general_settings)
        # Сигналы
        self.type_list.currentRowChanged.connect(self.update_hotkey_list)
        self.add_btn.clicked.connect(self.on_add)
        self.del_btn.clicked.connect(self.on_del)
        self.close_btn.clicked.connect(self.close)
        # Инициализация
        self.type_list.setCurrentRow(0)
        self.update_hotkey_list(0)

    def update_hotkey_list(self, idx):
        # Отключаем старый сигнал изменения чекбокса, чтобы не было дублирования
        try:
            self.hotkey_list.itemChanged.disconnect(self.on_hotkey_check_changed)
        except Exception:
            pass
        self.hotkey_list.clear()
        hotkeys = self.load_hotkeys()
        if idx == 0:
            filtered = [hk for hk in hotkeys if hk.get('type', 'keyboard') == 'keyboard']
        else:
            filtered = [hk for hk in hotkeys if hk.get('type') == 'trackpad']
        self._filtered = filtered
        for i, hk in enumerate(filtered):
            hk_type = hk.get('type', 'keyboard')
            disp = hk.get('combo', {}).get('disp') if hk_type == 'keyboard' else hk.get('gesture', '')
            action = hk.get('action', '')
            scope = hk.get('scope', 'global')
            app = hk.get('app', '')
            scope_disp = 'Глобальный' if scope == 'global' else f'Только для: {app}'
            action_disp = action
            if hk_type == 'trackpad' and action.startswith('hotkey:'):
                try:
                    import json
                    combo_data = json.loads(action[7:])
                    action_disp = f"Нажать: {combo_data.get('disp', 'Неизвестный хоткей')}"
                except Exception:
                    action_disp = "Ошибка парсинга хоткея"
            elif action.startswith('open '):
                action_disp = f"Открыть: {action[5:].strip()}"
            elif action.startswith('run '):
                action_disp = f"Запустить: {action[4:].strip()}"
            text = f"{disp}\n{action_disp}\n{scope_disp}"
            item = QtWidgets.QListWidgetItem(text)
            item.setSizeHint(QtCore.QSize(item.sizeHint().width(), 60))
            # --- Чекбокс сбоку ---
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Checked if hk.get('enabled', True) else QtCore.Qt.Unchecked)
            # --- Цвет для отключённых ---
            if not hk.get('enabled', True):
                item.setForeground(QtGui.QBrush(QtGui.QColor('gray')))
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
        self.hotkey_list.itemChanged.connect(self.on_hotkey_check_changed)

    def on_hotkey_check_changed(self, item):
         idx = self.hotkey_list.row(item)
         if idx < 0 or idx >= len(self._filtered):
             return
         hk = self._filtered[idx]
         hotkeys = self.load_hotkeys()
         # Найти и обновить в общем списке
         for i, h in enumerate(hotkeys):
             if h == hk:
                 new_state = (item.checkState() == QtCore.Qt.Checked)
                 hotkeys[i]['enabled'] = new_state
                 # Обновляем состояние в self._filtered, чтобы не сбрасывалось при смене селектора
                 self._filtered[idx]['enabled'] = new_state
                 break
         self.save_hotkeys(hotkeys)

    def show_hotkey_details(self, row):
        detail_row = row  # для фильтрации автосохранения при смене строки
        enabled_cb = None  # define to avoid NameError
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
            # временное хранение combo для восстановления при переключении типа действия
            temp_combo = {'combo': hk.get('combo', {}).copy()}
            combo_input.setText(hk.get('combo', {}).get('disp', ''))
            combo_input._mods = set(hk.get('combo', {}).get('mods', []))
            combo_input._vk = hk.get('combo', {}).get('vk')
            combo_input.setFixedWidth(180)
            grid.addWidget(QtWidgets.QLabel('Комбинация:'), row_idx, 0)
            grid.addWidget(combo_input, row_idx, 1)
            row_idx += 1
            # --- УДАЛЕНО: чекбокс включения хоткея ---
            # --- КОНЕЦ ДОБАВЛЕНИЯ ---

            # --- ДОБАВЛЕНО: Выбор области действия для клавиатуры ---
            scope_type = QtWidgets.QComboBox(details)
            scope_type.addItems(['Глобальный', 'Только для приложения'])
            scope_type.setCurrentIndex(0 if hk.get('scope', 'global') == 'global' else 1)
            grid.addWidget(QtWidgets.QLabel('Где работает хоткей:'), row_idx, 0)
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
            # --- КОНЕЦ ДОБАВЛЕНИЯ ---

        else: # trackpad
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
        action_type.addItems([
            'Открыть сайт',
            'Запустить программу/команду',
            'Нажать хоткей',
            'Установить яркость экрана',
            'Увеличить яркость экрана',
            'Уменьшить яркость экрана',
        ])
        # Определяем тип действия по существующему hk['action']
        action = hk.get('action', '')
        if action.startswith('open '):
            action_type.setCurrentIndex(0)
        elif action.startswith('run '):
            action_type.setCurrentIndex(1)
        elif action.startswith('hotkey:'):
            action_type.setCurrentIndex(2)
        elif action.startswith('brightness_set '):
            action_type.setCurrentIndex(3)
        elif action == 'brightness_up':
            action_type.setCurrentIndex(4)
        elif action == 'brightness_down':
            action_type.setCurrentIndex(5)
        else:
            # Если действие не задано, по умолчанию оставляем "Нажать хоткей"
            if not action:
                action_type.setCurrentIndex(2)
            else:
                action_type.setCurrentIndex(0)

        grid.addWidget(QtWidgets.QLabel('Тип действия:'), row_idx, 0)
        grid.addWidget(action_type, row_idx, 1)
        row_idx += 1
        action_input = QtWidgets.QLineEdit(details)
        hotkey_input = HotkeyInput(details)
        if action.startswith('open '):
            action_input.setText(hk.get('action', '')[5:].strip())
        elif action.startswith('run '):
            action_input.setText(hk.get('action', '')[4:].strip())
        if action.startswith('hotkey:'):
            import json
            try:
                combo = json.loads(hk.get('action', '')[7:])
                hotkey_input.setText(combo.get('disp', ''))
                hotkey_input._mods = set(combo.get('mods', []))
                hotkey_input._vk = combo.get('vk')
            except Exception:
                pass
        brightness_input = QtWidgets.QSpinBox(details)
        brightness_input.setRange(1, 100)
        brightness_input.setSuffix('%')
        brightness_input.setValue(85)
        brightness_input.setVisible(False)
        # Статическая разметка поля действия: URL/команда, хоткей, яркость
        label_action = QtWidgets.QLabel('URL или команда:')
        label_hotkey = QtWidgets.QLabel('Хоткей:')
        label_brightness = QtWidgets.QLabel('Яркость:')
        grid.addWidget(label_action, row_idx, 0)
        grid.addWidget(action_input, row_idx, 1)
        grid.addWidget(label_hotkey, row_idx, 0)
        grid.addWidget(hotkey_input, row_idx, 1)
        grid.addWidget(label_brightness, row_idx, 0)
        grid.addWidget(brightness_input, row_idx, 1)

        def set_action_field(idx):
            # Показывать/скрывать статически добавленные виджеты
            label_action.setVisible(idx in (0, 1))
            action_input.setVisible(idx in (0, 1))
            label_hotkey.setVisible(idx == 2)
            hotkey_input.setVisible(idx == 2)
            label_brightness.setVisible(idx == 3)
            brightness_input.setVisible(idx == 3)

        set_action_field(action_type.currentIndex())
        def on_action_type_change(idx):
            # при уходе с режима 'Нажать хоткей' сохраняем текущее combo
            if idx != 2:
                temp_combo['combo'] = combo_input.get_combo()
            # при возврате показываем последнюю введенную combo
            if idx == 2:
                combo = temp_combo['combo']
                combo_input.setText(combo.get('disp', ''))
                combo_input._mods = set(combo.get('mods', []))
                combo_input._vk = combo.get('vk')
            set_action_field(idx)
        # Сначала попытка отключить старую функцию (если она не подключена, игнорируем)
        try:
            action_type.currentIndexChanged.disconnect(on_action_type_change)
        except TypeError:
            pass
        action_type.currentIndexChanged.connect(on_action_type_change)

        def save_changes():
            hotkeys = self.load_hotkeys()
            current_hk_index = -1
            for i, h in enumerate(hotkeys):
                 if h == hk:
                     current_hk_index = i
                     break

            if current_hk_index == -1:
                print("Ошибка: Не удалось найти редактируемый хоткей в списке.")
                return # Не нашли хоткей, ничего не делаем

            original_hk = hotkeys[current_hk_index]  # Сохраняем оригинал для отката
            # Предыдущая combo: берем из UI, чтобы сохранить свежезахваченную комбинацию
            prev_combo = combo_input.get_combo()

            try:
                # Общая часть данных клавиатурного хоткея (тип, scope, app)
                if hk.get('type', 'keyboard') == 'keyboard':
                    scope = 'global' if scope_type.currentIndex() == 0 else 'app'
                    app = app_combo.currentText() if scope == 'app' else ''
                    new_hk_data = {
                        'type': 'keyboard',
                        'combo': prev_combo,  # combo всегда обновляется из UI
                        'gesture': '',
                        'scope': scope,
                        'app': app
                    }
                else:
                    gesture = gesture_combo.currentText()
                    scope = 'global' if scope_type.currentIndex() == 0 else 'app'
                    app = app_combo.currentText() if scope == 'app' else ''
                    new_hk_data = {
                        'type': 'trackpad',
                        'combo': None,
                        'gesture': gesture,
                        'scope': scope,
                        'app': app
                    }
                # Определяем действие и, при необходимости, combo
                action_idx = action_type.currentIndex()
                if action_idx == 0:
                    action = f'open {action_input.text().strip()}'
                elif action_idx == 1:
                    action = f'run {action_input.text().strip()}'
                elif action_idx == 2:  # Нажать хоткей — используем ввод combo
                    combo = combo_input.get_combo()
                    # валидация combo
                    if combo.get('vk') is None:
                        combo = original_hk.get('combo', {})
                    new_hk_data['combo'] = combo
                    action = 'hotkey:' + json.dumps(combo, ensure_ascii=False)
                elif action_idx == 3:
                    action = f'brightness_set {brightness_input.value()}'
                elif action_idx == 4:
                    action = 'brightness_up'
                elif action_idx == 5:
                    action = 'brightness_down'
                # Если действие не связано с хоткеем, сохраняем combo из UI (prev_combo), а не из файла
                if action_idx != 2:
                    new_hk_data['combo'] = prev_combo
                new_hk_data['action'] = action

                # --- ДОБАВЛЕНИЕ: сохраняем состояние enabled (с защитой от NameError) ---
                try:
                    new_hk_data['enabled'] = enabled_cb.isChecked()
                except NameError:
                    new_hk_data['enabled'] = hk.get('enabled', True)

                # Обновляем хоткей в списке только если что-то изменилось
                if hotkeys[current_hk_index] != new_hk_data:
                    hotkeys[current_hk_index] = new_hk_data
                    self.save_hotkeys(hotkeys)
                    # Обновляем in-memory данные, чтобы UI при переключении не сбрасывалась введённая combo
                    self._filtered[current_hk_index] = new_hk_data
                    print("Хоткей успешно сохранен. Перерегистрация произойдет автоматически.")

            except Exception as save_err:
                 print(f"Критическая ошибка при сохранении изменений хоткея: {save_err}")

        # Подключаем сигналы к save_changes
        if hk.get('type', 'keyboard') == 'keyboard':
            # Используем editingFinished для сохранения после завершения ввода
            combo_input.editingFinished.connect(save_changes)
            # --- ДОБАВЛЕНО: Подключаем scope/app ---
            scope_type.currentIndexChanged.connect(save_changes)
            app_combo.currentIndexChanged.connect(save_changes)
            # --- КОНЕЦ ДОБАВЛЕНИЯ ---
        else: # trackpad
            gesture_combo.currentIndexChanged.connect(save_changes)
            scope_type.currentIndexChanged.connect(save_changes)
            app_combo.currentIndexChanged.connect(save_changes) # Или editingFinished, если разрешен ввод

        action_input.editingFinished.connect(save_changes)
        hotkey_input.editingFinished.connect(save_changes)
        # Сохраняем изменения яркости, когда пользователь меняет значение
        brightness_input.valueChanged.connect(save_changes)

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
        print("Хоткей удален. Перерегистрация произойдет автоматически.") # Убрали прямой вызов register_hotkeys
        # try:
        #     import main
        #     main.register_hotkeys() # <--- УДАЛЕНО
        # except Exception as e:
        #     print(f'Ошибка перерегистрации хоткеев: {e}')

    def _add_keyboard_hotkey(self):
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle('Добавить клавиатурный хоткей')
        vbox = QtWidgets.QVBoxLayout()
        hotkey_input = QtWidgets.QLineEdit()
        hotkey_input.setReadOnly(True)
        vbox.addWidget(QtWidgets.QLabel('Комбинация:'))
        vbox.addWidget(hotkey_input)
        # --- действия для яркости ---
        action_type = QtWidgets.QComboBox()
        action_type.addItems([
            'Открыть сайт',
            'Запустить программу/команду',
            'Нажать хоткей',
            'Установить яркость экрана',
            'Увеличить яркость экрана',
            'Уменьшить яркость экрана',
        ])
        vbox.addWidget(QtWidgets.QLabel('Тип действия:'))
        vbox.addWidget(action_type)
        action_input = QtWidgets.QLineEdit()
        vbox.addWidget(QtWidgets.QLabel('URL или команда:'))
        vbox.addWidget(action_input)
        brightness_input = QtWidgets.QSpinBox()
        brightness_input.setRange(1, 100)
        brightness_input.setSuffix('%')
        brightness_input.setValue(85)
        brightness_input.setVisible(False)
        # Статическая разметка поля действия: URL/команда, хоткей, яркость
        label_action = QtWidgets.QLabel('URL или команда:')
        label_hotkey = QtWidgets.QLabel('Хоткей:')
        label_brightness = QtWidgets.QLabel('Яркость:')
        grid.addWidget(label_action, row_idx, 0)
        grid.addWidget(action_input, row_idx, 1)
        grid.addWidget(label_hotkey, row_idx, 0)
        grid.addWidget(hotkey_input, row_idx, 1)
        grid.addWidget(label_brightness, row_idx, 0)
        grid.addWidget(brightness_input, row_idx, 1)

        def set_action_field(idx):
            # Показывать/скрывать статически добавленные виджеты
            label_action.setVisible(idx in (0, 1))
            action_input.setVisible(idx in (0, 1))
            label_hotkey.setVisible(idx == 2)
            hotkey_input.setVisible(idx == 2)
            label_brightness.setVisible(idx == 3)
            brightness_input.setVisible(idx == 3)

        set_action_field(action_type.currentIndex())
        action_type.currentIndexChanged.connect(set_action_field)
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
        # --- subprocess для захвата хоткея ---
        hotkey_input.setText('Нажмите любую клавишу...')
        combo = {'mods': [], 'vk': None, 'disp': ''}
        timer_ref = {'active': True}  # Для остановки таймера при закрытии
        def start_hotkey_capture():
            import subprocess, sys, os, json
            proc = subprocess.Popen([
                sys.executable, os.path.join(os.path.dirname(__file__), 'hotkey_capture_helper.py')
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            def check_proc():
                if not timer_ref['active']:
                    return
                ret = proc.poll()
                if ret is None:
                    QtCore.QTimer.singleShot(50, check_proc)
                    return
                out, err = proc.communicate()
                try:
                    data = json.loads(out.decode('utf-8').strip())
                    vk = data.get('vk')
                    mods = set(data.get('mods', []))
                    fn_names = {
                        122: 'Яркость -', 120: 'Яркость +', 113: 'Яркость +', 107: 'Яркость -',
                        145: 'Подсветка клавиатуры +', 144: 'Подсветка клавиатуры -',
                        72: 'Громкость +', 73: 'Громкость -', 74: 'Mute', 16: 'Play/Pause', 17: 'Next', 15: 'Prev',
                        99: 'F3', 118: 'F4', 96: 'F5', 97: 'F6', 98: 'F7', 100: 'F8', 101: 'F9', 109: 'F10', 103: 'F11', 111: 'F12',
                    }
                    # По возможности отображаем цифры и буквы
                    digit_map = {29:'0',18:'1',19:'2',20:'3',21:'4',23:'5',22:'6',26:'7',28:'8',25:'9'}
                    letter_map = {0:'A',11:'B',8:'C',2:'D',14:'E',3:'F',5:'G',4:'H',34:'I',38:'J',40:'K',37:'L',46:'M',45:'N',31:'O',35:'P',12:'Q',15:'R',1:'S',17:'T',32:'U',9:'V',13:'W',7:'X',16:'Y',6:'Z'}
                    if vk in digit_map:
                        key_name = digit_map[vk]
                    elif vk in letter_map:
                        key_name = letter_map[vk]
                    else:
                        key_name = fn_names.get(vk, f'VK_{vk}')
                    mods_disp = ' + '.join(sorted(mods))
                    combo['mods'] = sorted(list(mods))
                    combo['vk'] = vk
                    combo['disp'] = (mods_disp + (' + ' if mods_disp else '') + key_name).strip()
                    if hotkey_input and not sip.isdeleted(hotkey_input):
                        hotkey_input.setText(combo['disp'])
                except Exception:
                    if hotkey_input and not sip.isdeleted(hotkey_input):
                        hotkey_input.setText('<Ошибка захвата хоткея>')
            QtCore.QTimer.singleShot(50, check_proc)
        def on_close():
            timer_ref['active'] = False
        dlg.finished.connect(on_close)
        hotkey_input.mousePressEvent = lambda event: start_hotkey_capture()
        start_hotkey_capture()
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            action = ''
            idx = action_type.currentIndex()
            if idx == 0:
                action = f'open {action_input.text().strip()}'
            elif idx == 1:
                action = f'run {action_input.text().strip()}'
            elif idx == 2:
                import json
                action = 'hotkey:' + json.dumps(combo, ensure_ascii=False)
            elif idx == 3:
                action = f'brightness_set {brightness_input.value()}'
            elif idx == 4:
                action = 'brightness_up'
            elif idx == 5:
                action = 'brightness_down'
            scope = 'global' if scope_type.currentIndex() == 0 else 'app'
            app = app_combo.currentText() if scope == 'app' else ''
            if combo and action and combo['vk'] is not None:
                hotkeys = self.load_hotkeys()
                hotkeys.append({'type': 'keyboard', 'combo': combo, 'gesture': '', 'action': action, 'scope': scope, 'app': app})
                self.save_hotkeys(hotkeys)
                print("Клавиатурный хоткей добавлен. Перерегистрация произойдет автоматически.")

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
                print("Трекпад-жест добавлен. Перерегистрация произойдет автоматически.") # Убрали прямой вызов register_hotkeys
                # try:
                #     import main
                #     main.register_hotkeys() # <--- УДАЛЕНО
                # except Exception as e:
                #     print(f'Ошибка перерегистрации хоткеев: {e}')

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
                print("Клавиатурный хоткей изменен. Перерегистрация произойдет автоматически.") # Убрали прямой вызов register_hotkeys
                # try:
                #     import main
                #     main.register_hotkeys() # <--- УДАЛЕНО
                # except Exception as e:
                #     print(f'Ошибка перерегистрации хоткеев: {e}')

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
                print("Трекпад-жест изменен. Перерегистрация произойдет автоматически.") # Убрали прямой вызов register_hotkeys
                # try:
                #     import main
                #     main.register_hotkeys() # <--- УДАЛЕНО
                # except Exception as e:
                #     print(f'Ошибка перерегистрации хоткеев: {e}')

    def load_general_settings(self):
        import os, json
        path = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'HotkeyMaster', 'settings.json')
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.autostart_cb.setChecked(data.get('autostart', False))
            except Exception:
                pass
        else:
            self.autostart_cb.setChecked(False)

    def save_general_settings(self):
        import os, json
        path = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'HotkeyMaster', 'settings.json')
        data = {
            'autostart': self.autostart_cb.isChecked(),
        }
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        # --- Реализация автостарта ---
        if data['autostart']:
            self.enable_autostart()
        else:
            self.disable_autostart()

    def enable_autostart(self):
        import subprocess, os
        app_path = os.path.abspath(sys.argv[0])
        script = f'''osascript -e 'tell application "System Events" to make login item at end with properties {{path:"{app_path}", hidden:false}}'''
        try:
            subprocess.run(script, shell=True)
        except Exception:
            pass

    def disable_autostart(self):
        import subprocess
        script = '''osascript -e 'tell application "System Events" to delete login item "HotkeyMaster"' '''
        try:
            subprocess.run(script, shell=True)
        except Exception:
            pass

def show_settings_window(load_hotkeys, save_hotkeys):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    win = SettingsWindow(load_hotkeys, save_hotkeys)
    win.setWindowModality(QtCore.Qt.ApplicationModal)
    # Показываем и поднимаем окно в передний план
    win.show()
    win.raise_()
    win.activateWindow()
    win.exec_()
