"""Настройки HotkeyMaster — стабильная переработанная версия UI."""
from PyQt5 import QtWidgets, QtCore, QtGui
import sys, os, json, logging

logger = logging.getLogger('hotkeymaster.ui')

# ---------------- Key mapping ----------------
_BASE = {
    65:0,66:11,67:8,68:2,69:14,70:3,71:5,72:4,73:34,74:38,75:40,76:37,77:46,78:45,79:31,80:35,81:12,82:15,83:1,84:17,85:32,86:9,87:13,88:7,89:16,90:6,
    48:29,49:18,50:19,51:20,52:21,53:23,54:22,55:26,56:28,57:25,
    QtCore.Qt.Key_F1:122, QtCore.Qt.Key_F2:120, QtCore.Qt.Key_F3:99, QtCore.Qt.Key_F4:118,
    QtCore.Qt.Key_F5:96, QtCore.Qt.Key_F6:97, QtCore.Qt.Key_F7:98, QtCore.Qt.Key_F8:100,
    QtCore.Qt.Key_F9:101, QtCore.Qt.Key_F10:109, QtCore.Qt.Key_F11:103, QtCore.Qt.Key_F12:111,
    QtCore.Qt.Key_Return:36, QtCore.Qt.Key_Enter:76, QtCore.Qt.Key_Tab:48, QtCore.Qt.Key_Escape:53,
    QtCore.Qt.Key_Space:49, QtCore.Qt.Key_Backspace:51, QtCore.Qt.Key_Delete:117,
    QtCore.Qt.Key_Left:123, QtCore.Qt.Key_Right:124, QtCore.Qt.Key_Up:126, QtCore.Qt.Key_Down:125,
}
_FN = {
    QtCore.Qt.Key_MonBrightnessUp:113, QtCore.Qt.Key_MonBrightnessDown:107,
    QtCore.Qt.Key_VolumeUp:72, QtCore.Qt.Key_VolumeDown:73, QtCore.Qt.Key_VolumeMute:74
}
_REV_LET = {0:'A',11:'B',8:'C',2:'D',14:'E',3:'F',5:'G',4:'H',34:'I',38:'J',40:'K',37:'L',46:'M',45:'N',31:'O',35:'P',12:'Q',15:'R',1:'S',17:'T',32:'U',9:'V',13:'W',7:'X',16:'Y',6:'Z'}
_REV_DIG = {29:'0',18:'1',19:'2',20:'3',21:'4',23:'5',22:'6',26:'7',28:'8',25:'9'}
_REV_FN = {122:'F1',120:'F2',99:'F3',118:'F4',96:'F5',97:'F6',98:'F7',100:'F8',101:'F9',109:'F10',103:'F11',111:'F12'}
_MOD_KEYS = {QtCore.Qt.Key_Control, QtCore.Qt.Key_Shift, QtCore.Qt.Key_Alt, QtCore.Qt.Key_Meta, QtCore.Qt.Key_Super_L, QtCore.Qt.Key_Super_R}

def _qt_to_vk(k):
    return _FN.get(k, _BASE.get(k))


class HotkeyInput(QtWidgets.QLineEdit):
    ORDER = ['ctrl', 'alt', 'shift', 'cmd']
    def __init__(self, parent=None, callback=None):
        super().__init__(parent)
        self._mods=set(); self._vk=None; self._disp=''; self._cb=callback
        self.setReadOnly(True); self.setPlaceholderText('Нажмите комбинацию...')

    def keyPressEvent(self, e: QtGui.QKeyEvent):
        if e.isAutoRepeat(): e.accept(); return
        self._mods.clear(); m=e.modifiers()
        # На некоторых конфигурациях macOS Qt путает Control / Command (Meta) – добавим корректировку
        if sys.platform == 'darwin':
            # Обнаруженный инверс: ControlModifier соответствует фактической Cmd, MetaModifier -> Ctrl
            if m & QtCore.Qt.ControlModifier: self._mods.add('cmd')
            if m & QtCore.Qt.MetaModifier: self._mods.add('ctrl')
        else:
            if m & QtCore.Qt.ControlModifier: self._mods.add('ctrl')
            if m & QtCore.Qt.MetaModifier: self._mods.add('cmd')
        if m & QtCore.Qt.AltModifier: self._mods.add('alt')
        if m & QtCore.Qt.ShiftModifier: self._mods.add('shift')
        k=e.key()
        if k not in _MOD_KEYS:
            vk=_qt_to_vk(k)
            if vk is not None: self._vk=vk
        key=''
        if self._vk is not None:
            if self._vk in _REV_DIG: key=_REV_DIG[self._vk]
            elif self._vk in _REV_LET: key=_REV_LET[self._vk]
            else: key=_REV_FN.get(self._vk, f'VK_{self._vk}')
        parts=[m.capitalize() for m in self.ORDER if m in self._mods]
        if key: parts.append(key)
        self._disp=' + '.join(parts) or '...'; self.setText(self._disp)
        if self._cb: QtCore.QTimer.singleShot(0, self._cb)
        e.accept()

    def keyReleaseEvent(self, e): e.accept()
    def get_combo(self): return {'mods':sorted(self._mods), 'vk':self._vk, 'disp':(self._disp if self._vk is not None else '')}


def get_applications():
    res=[]
    try:
        for n in os.listdir('/Applications'):
            if n.endswith('.app'):
                res.append(n[:-4])
    except Exception:
        pass
    return sorted(res)


class SettingsWindow(QtWidgets.QDialog):
    def __init__(self, load_hotkeys, save_hotkeys):
        super().__init__()
        self.load_hotkeys = load_hotkeys
        self.save_hotkeys = save_hotkeys
        logger.debug('Init SettingsWindow')
        self.setWindowTitle('HotkeyMaster — Настройки')
        self.resize(900, 560)

        # --- Основная раскладка ---
        root = QtWidgets.QVBoxLayout(self)
        top = QtWidgets.QHBoxLayout()
        root.addLayout(top)

        # Левая колонка разделов
        self.sections = QtWidgets.QListWidget()
        self.sections.addItems(['Общие', 'Клавиатура', 'Трекпад'])
        self.sections.setMaximumWidth(140)
        top.addWidget(self.sections)

        # Контейнер списка хоткеев (чтобы легко скрывать целиком)
        self.hk_container = QtWidgets.QWidget()
        hk_v = QtWidgets.QVBoxLayout(self.hk_container)
        hk_v.setContentsMargins(0,0,0,0)
        self.hk_list = QtWidgets.QListWidget()
        self.hk_list.setWordWrap(True)
        hk_v.addWidget(self.hk_list)
        top.addWidget(self.hk_container, 1)

        # Scroll с правой страницей
        self.detail_scroll = QtWidgets.QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        top.addWidget(self.detail_scroll, 2)

        # Кнопки
        btns = QtWidgets.QHBoxLayout()
        self.btn_add = QtWidgets.QPushButton('Добавить')
        self.btn_del = QtWidgets.QPushButton('Удалить')
        b_close = QtWidgets.QPushButton('Закрыть')
        btns.addWidget(self.btn_add)
        btns.addWidget(self.btn_del)
        btns.addStretch()
        btns.addWidget(b_close)
        root.addLayout(btns)

        # --- Группы общих настроек ---
        self.grp_general = QtWidgets.QGroupBox('Общие настройки')
        gl = QtWidgets.QVBoxLayout(self.grp_general)
        self.cb_autostart = QtWidgets.QCheckBox('Автостарт при входе в macOS')
        self.cb_strict = QtWidgets.QCheckBox('Строгое совпадение модификаторов')
        gl.addWidget(self.cb_autostart)
        gl.addWidget(self.cb_strict)

        self.grp_track = QtWidgets.QGroupBox('Трекпад — глобальные параметры')
        fl = QtWidgets.QFormLayout(self.grp_track)
        self.sb_debounce = QtWidgets.QDoubleSpinBox(); self.sb_debounce.setRange(0,3); self.sb_debounce.setDecimals(2); self.sb_debounce.setSingleStep(0.05); self.sb_debounce.setValue(0.60)
        self.sb_release = QtWidgets.QDoubleSpinBox(); self.sb_release.setRange(0,0.5); self.sb_release.setDecimals(3); self.sb_release.setSingleStep(0.01); self.sb_release.setValue(0.02)
        fl.addRow('Повтор жеста (сек):', self.sb_debounce)
        fl.addRow('Мин. разрыв тапов (сек):', self.sb_release)

        # --- Стек страниц ---
        self._stack_container = QtWidgets.QWidget()
        self._stack = QtWidgets.QStackedLayout(self._stack_container)
        self._page_general = QtWidgets.QWidget()
        pg_l = QtWidgets.QVBoxLayout(self._page_general)
        pg_l.addWidget(self.grp_general)
        pg_l.addWidget(self.grp_track)
        pg_l.addStretch()
        self._page_details = QtWidgets.QWidget()
        self._details_layout = QtWidgets.QGridLayout(self._page_details)
        self._details_layout.setColumnStretch(1, 1)
        self._stack.addWidget(self._page_general)
        self._stack.addWidget(self._page_details)
        self.detail_scroll.setWidget(self._stack_container)

        # --- Путь настроек ---
        self._settings_path = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'HotkeyMaster', 'settings.json')
        self._load_general(); self._load_win_size(); self._install_size_saver()

        # Сигналы сохранения общих настроек
        for w in (self.cb_autostart, self.cb_strict, self.sb_debounce, self.sb_release):
            if isinstance(w, QtWidgets.QCheckBox):
                w.stateChanged.connect(self._save_general)
            else:
                w.valueChanged.connect(self._save_general)
        self.sections.currentRowChanged.connect(self._populate)
        self.hk_list.currentRowChanged.connect(self._show_details)
        self.btn_add.clicked.connect(self._add)
        self.btn_del.clicked.connect(self._del)
        b_close.clicked.connect(self.close)

        # Стартовое заполнение
        self.sections.setCurrentRow(0)
        self._populate(0)

    # ---------- window size persistence ----------
    def _load_win_size(self):
        if not os.path.exists(self._settings_path): return
        try:
            with open(self._settings_path,'r',encoding='utf-8') as f: d=json.load(f)
            s=d.get('window_size')
            if isinstance(s,list) and len(s)==2: self.resize(*s)
        except Exception:
            pass

    def _install_size_saver(self):
        orig=self.resizeEvent
        def wrap(ev):
            try:
                data={}
                if os.path.exists(self._settings_path):
                    with open(self._settings_path,'r',encoding='utf-8') as f: data=json.load(f)
                data['window_size']=[self.width(), self.height()]
                os.makedirs(os.path.dirname(self._settings_path), exist_ok=True)
                with open(self._settings_path,'w',encoding='utf-8') as f: json.dump(data,f,ensure_ascii=False,indent=2)
            except Exception:
                pass
            orig(ev)
        self.resizeEvent=wrap

    # ---------- formatting helpers ----------
    def _fmt(self, t, a):
        if t == 'trackpad' and a.startswith('hotkey:'):
            try:
                return 'Нажать: ' + json.loads(a[7:]).get('disp', '?')
            except Exception:
                return 'Ошибка'
        # сначала open_app чтобы не перехватила проверка open
        if a.startswith('open_app '):
            return 'Открыть приложение: ' + a[9:].strip()
        if a.startswith('open '):
            return 'Открыть: ' + a[5:].strip()
        if a.startswith('run '):
            return 'Запустить: ' + a[4:].strip()
        if a.startswith('hotkey:'):
            try:
                return 'Нажать: ' + json.loads(a[7:]).get('disp', '?')
            except Exception:
                return 'Ошибка'
        if a.startswith('brightness_set '):
            try:
                return f"Яркость: {int(a.split()[1])}%"
            except Exception:
                return 'Яркость'
        if a == 'brightness_up':
            return 'Увеличить яркость'
        if a == 'brightness_down':
            return 'Уменьшить яркость'
        return a or '—'

    # ---------- section population ----------
    def _populate(self, idx):
        logger.debug('Populate idx=%s', idx)
        if idx==0:
            # Вкладка "Общие": прячем контейнер хоткеев и кнопки
            self.hk_list.clear()
            self.hk_list.setEnabled(False)
            self.hk_container.hide()
            self.btn_add.hide(); self.btn_del.hide()
            self.btn_add.setEnabled(False); self.btn_del.setEnabled(False)
            self._filtered = []
            self._stack.setCurrentIndex(0)
            return
        # остальные вкладки
        self.hk_container.show()
        self.hk_list.show()
        self.hk_list.setEnabled(True)
        self.btn_add.show(); self.btn_del.show()
        self.btn_add.setEnabled(True); self.btn_del.setEnabled(True)
        self._stack.setCurrentIndex(1)
        t='keyboard' if idx==1 else 'trackpad'
        try: self.hk_list.itemChanged.disconnect(self._toggle)
        except Exception: pass
        self.hk_list.clear(); all_h=self.load_hotkeys(); self._filtered=[h for h in all_h if h.get('type','keyboard')==t]
        for h in self._filtered:
            disp=h.get('combo',{}).get('disp') if t=='keyboard' else h.get('gesture','')
            act=self._fmt(t,h.get('action',''))
            scope=h.get('scope','global'); app=h.get('app',''); scope_txt='Глобальный' if scope=='global' else f'Только для: {app}'
            it=QtWidgets.QListWidgetItem(f"{disp}\n{act}\n{scope_txt}")
            it.setFlags(it.flags()|QtCore.Qt.ItemIsUserCheckable)
            it.setCheckState(QtCore.Qt.Checked if h.get('enabled',True) else QtCore.Qt.Unchecked)
            if not h.get('enabled',True): it.setForeground(QtGui.QBrush(QtGui.QColor('gray')))
            it.setSizeHint(QtCore.QSize(it.sizeHint().width(),60)); self.hk_list.addItem(it)
        self.hk_list.itemChanged.connect(self._toggle)
        if self.hk_list.count(): self.hk_list.setCurrentRow(0)
        else: self._show_details(-1)
        logger.debug('Hotkeys listed=%d', self.hk_list.count())

    def _toggle(self, item: QtWidgets.QListWidgetItem):
        r=self.hk_list.row(item)
        if r<0 or r>=len(self._filtered): return
        hk=self._filtered[r]; hs=self.load_hotkeys()
        for i,h in enumerate(hs):
            if h==hk: hs[i]['enabled']=(item.checkState()==QtCore.Qt.Checked); break
        self.save_hotkeys(hs)

    # ---------- details page ----------
    def _clear_details(self):
        while self._details_layout.count():
            it=self._details_layout.takeAt(0); w=it.widget()
            if w: w.deleteLater()
        if hasattr(self._page_details,'_w'): delattr(self._page_details,'_w')

    def _show_details(self, row):
        logger.debug('Show details row=%s', row)
        if row<0 or row>=len(getattr(self,'_filtered',[])):
            self._clear_details(); return
        hk=self._filtered[row]; self._clear_details(); grid=self._details_layout; r=0
        if hk.get('type')=='keyboard':
            combo=HotkeyInput(self._page_details, callback=lambda: self._save_inline(row))
            data=hk.get('combo',{}); combo.setText(data.get('disp','')); combo._mods=set(data.get('mods',[])); combo._vk=data.get('vk'); combo._disp=data.get('disp','')
            grid.addWidget(QtWidgets.QLabel('Комбинация:'),r,0); grid.addWidget(combo,r,1); r+=1
        else:
            gesture=QtWidgets.QComboBox(self._page_details)
            gesture.addItems(['Тап одним пальцем','Тап двумя пальцами','Тап тремя пальцами','Тап четырьмя пальцами'])
            if hk.get('gesture'):
                i=gesture.findText(hk.get('gesture'))
                if i>=0: gesture.setCurrentIndex(i)
            gesture.currentIndexChanged.connect(lambda _ : self._save_inline(row))
            grid.addWidget(QtWidgets.QLabel('Жест:'),r,0); grid.addWidget(gesture,r,1); r+=1
        scope_box=QtWidgets.QComboBox(self._page_details); scope_box.addItems(['Глобальный','Только для приложения']); scope_box.setCurrentIndex(0 if hk.get('scope','global')=='global' else 1)
        scope_box.currentIndexChanged.connect(lambda _ : self._save_inline(row))
        grid.addWidget(QtWidgets.QLabel('Область:'),r,0); grid.addWidget(scope_box,r,1); r+=1
        # Комбо для ограничения области действием конкретного активного приложения
        app_box=QtWidgets.QComboBox(self._page_details); app_box.addItems(['']+get_applications()); app_box.setEnabled(scope_box.currentIndex()==1)
        if hk.get('app'):
            i=app_box.findText(hk.get('app'))
            if i>=0: app_box.setCurrentIndex(i)
        label_app_scope=QtWidgets.QLabel('Для приложения:')
        def _scope_vis(i):
            app_box.setEnabled(i==1); vis=(i==1); label_app_scope.setVisible(vis); app_box.setVisible(vis)
        scope_box.currentIndexChanged.connect(_scope_vis)
        app_box.currentIndexChanged.connect(lambda _ : self._save_inline(row))
        grid.addWidget(label_app_scope,r,0); grid.addWidget(app_box,r,1); r+=1
        _scope_vis(scope_box.currentIndex())  # начальная видимость
        # --- Группа действия ---
        act_group=QtWidgets.QGroupBox('Действие')
        act_form=QtWidgets.QFormLayout(act_group); act_form.setLabelAlignment(QtCore.Qt.AlignRight)
        grid.addWidget(act_group,r,0,1,2); r+=1
        act_type=QtWidgets.QComboBox(act_group)
        act_type.addItems(['Открыть сайт','Открыть приложение','Запустить программу/команду','Нажать хоткей','Установить яркость экрана','Увеличить яркость','Уменьшить яркость'])
        act=hk.get('action',''); patt=[('open_app ',1),('open ',0),('run ',2),('hotkey:',3),('brightness_set ',4),('brightness_up',5),('brightness_down',6)]
        for p,i in patt:
            if act.startswith(p): act_type.setCurrentIndex(i); break
        act_form.addRow('Тип:', act_type)
        line=QtWidgets.QLineEdit(act_group)
        if act.startswith('open '): line.setText(act[5:].strip())
        elif act.startswith('run '): line.setText(act[4:].strip())
        app_action_box=QtWidgets.QComboBox(act_group); app_action_box.addItems(['']+get_applications())
        if act.startswith('open_app '):
            cur_app=act[9:].strip(); i=app_action_box.findText(cur_app)
            if i>=0: app_action_box.setCurrentIndex(i)
        app_action_box.currentIndexChanged.connect(lambda _ : self._save_inline(row))
        hk_act=HotkeyInput(act_group, callback=lambda: self._save_inline(row))
        if act.startswith('hotkey:'):
            try:
                c=json.loads(act[7:]); hk_act.setText(c.get('disp','')); hk_act._mods=set(c.get('mods',[])); hk_act._vk=c.get('vk'); hk_act._disp=c.get('disp','')
            except Exception: pass
        bright=QtWidgets.QSpinBox(act_group); bright.setRange(1,100); bright.setValue(85)
        if act.startswith('brightness_set '):
            try: bright.setValue(int(act.split()[1]))
            except Exception: pass
        act_form.addRow('URL / Команда:', line)
        act_form.addRow('Приложение:', app_action_box)
        act_form.addRow('Хоткей:', hk_act)
        act_form.addRow('Яркость (%):', bright)
        def _adj(i):
            line.setVisible(i in (0,2))
            act_form.labelForField(line).setVisible(i in (0,2))
            app_action_box.setVisible(i==1); act_form.labelForField(app_action_box).setVisible(i==1)
            hk_act.setVisible(i==3); act_form.labelForField(hk_act).setVisible(i==3)
            bright.setVisible(i==4); act_form.labelForField(bright).setVisible(i==4)
        act_type.currentIndexChanged.connect(lambda i: (_adj(i), self._save_inline(row)))
        line.editingFinished.connect(lambda: self._save_inline(row)); bright.valueChanged.connect(lambda _ : self._save_inline(row))
        _adj(act_type.currentIndex())
        self._page_details._w={'combo':locals().get('combo'),'gesture':locals().get('gesture'),'scope':scope_box,'app':app_box,'atype':act_type,'line':line,'hk_act':hk_act,'bright':bright,'app_action':app_action_box}
        self._cur=row

    def _save_inline(self,row):
        if row!=getattr(self,'_cur',-1) or row<0 or row>=len(self._filtered): return
        if not hasattr(self._page_details,'_w'): return
        hk=self._filtered[row]; w=self._page_details._w
        new={'type':hk.get('type','keyboard'),'enabled':hk.get('enabled',True)}
        scope_box=w['scope']; app_box=w['app']; scope='global' if scope_box.currentIndex()==0 else 'app'; new['scope']=scope; new['app']=app_box.currentText() if scope=='app' else ''
        if new['type']=='keyboard':
            combo=w['combo']; new['combo']=combo.get_combo() if combo else {'mods':[], 'vk':None,'disp':''}; new['gesture']=''
        else:
            gest=w['gesture']; new['gesture']=gest.currentText() if gest else ''; new['combo']=None
        at=w['atype'].currentIndex(); old_action=hk.get('action','')
        if at==0:
            new['action']='open '+w['line'].text().strip()
        elif at==1:
            app_sel=w['app_action'].currentText().strip()
            logger.debug('SaveInline open_app selection raw=%r old_action=%r', app_sel, old_action)
            if app_sel:
                new['action']='open_app '+app_sel
                logger.debug('Assigned new open_app action=%s', new['action'])
            else:
                # сохраняем прежнее действие, чтобы не терять ранее выбранное приложение
                new['action']= old_action
                logger.debug('Empty app selection keep previous action=%r', new['action'])
        elif at==2:
            new['action']='run '+w['line'].text().strip()
        elif at==3:
            new['action']='hotkey:'+json.dumps(w['hk_act'].get_combo(), ensure_ascii=False)
        elif at==4:
            new['action']=f"brightness_set {w['bright'].value()}"
        elif at==5:
            new['action']='brightness_up'
        elif at==6:
            new['action']='brightness_down'
        hs=self.load_hotkeys()
        for i,h in enumerate(hs):
            if h==hk and h!=new:
                logger.debug('Updating hotkey row=%d old_action=%r new_action=%r', row, hk.get('action'), new.get('action'))
                hs[i]=new; self.save_hotkeys(hs); self._filtered[row]=new
                disp=new.get('combo',{}).get('disp') if new['type']=='keyboard' else new.get('gesture','')
                act=self._fmt(new['type'], new.get('action',''))
                scope_txt='Глобальный' if new['scope']=='global' else f"Только для: {new.get('app','')}"
                it=self.hk_list.item(row)
                if it: it.setText(f"{disp}\n{act}\n{scope_txt}")
                break

    # ---------- add/delete ----------
    def _add(self):
        idx=self.sections.currentRow(); t='keyboard' if idx==1 else 'trackpad'
        if t=='keyboard': new={'type':'keyboard','combo':{'mods':[], 'vk':None,'disp':''},'action':'open https://','scope':'global','app':'','enabled':True,'gesture':''}
        else: new={'type':'trackpad','gesture':'Тап двумя пальцами','action':'open https://','scope':'global','app':'','enabled':True,'combo':None}
        hs=self.load_hotkeys(); hs.append(new); self.save_hotkeys(hs); self._populate(idx); self.hk_list.setCurrentRow(self.hk_list.count()-1)

    def _del(self):
        idx=self.sections.currentRow(); row=self.hk_list.currentRow()
        if idx==0 or row<0 or row>=len(self._filtered): return
        tgt=self._filtered[row]; hs=self.load_hotkeys()
        for i,h in enumerate(hs):
            if h==tgt: del hs[i]; break
        self.save_hotkeys(hs); self._populate(idx)

    # ---------- general settings ----------
    def _load_general(self):
        data={}
        try:
            with open(self._settings_path,'r',encoding='utf-8') as f: data=json.load(f)
        except Exception: pass
        actual=False
        try:
            from autolaunch import AutoLaunchManager
            actual=AutoLaunchManager.is_autolaunch_enabled()
        except Exception: pass
        self.cb_autostart.setChecked(actual)
        self.cb_strict.setChecked(bool(data.get('strict_mod_match',False)))
        gd=data.get('gesture_debounce'); rg=data.get('gesture_release_gap')
        if isinstance(gd,(int,float)) and 0<=gd<=3: self.sb_debounce.setValue(float(gd))
        if isinstance(rg,(int,float)) and 0<=rg<=0.5: self.sb_release.setValue(float(rg))

    def _save_general(self):
        data={'autostart':self.cb_autostart.isChecked(),'strict_mod_match':self.cb_strict.isChecked(),'gesture_debounce':round(self.sb_debounce.value(),2),'gesture_release_gap':round(self.sb_release.value(),3)}
        try:
            os.makedirs(os.path.dirname(self._settings_path),exist_ok=True)
            with open(self._settings_path,'w',encoding='utf-8') as f: json.dump(data,f,ensure_ascii=False,indent=2)
        except Exception: pass
        try:
            from autolaunch import AutoLaunchManager
            if data['autostart']: AutoLaunchManager.enable_autostart()
            else: AutoLaunchManager.disable_autostart()
        except Exception: pass


_settings_window_ref = None

def show_settings_window(load_hotkeys, save_hotkeys):
    """Открыть окно настроек (гарантируя один экземпляр)."""
    global _settings_window_ref
    logger.debug('Open settings window request')
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    # Если уже открыто – просто сфокусируем
    if _settings_window_ref and _settings_window_ref.isVisible():
        logger.debug('Settings window already open, focusing')
        _settings_window_ref.raise_(); _settings_window_ref.activateWindow(); return
    win = SettingsWindow(load_hotkeys, save_hotkeys)
    _settings_window_ref = win
    win.setWindowModality(QtCore.Qt.ApplicationModal)
    win.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
    # Очистим ссылку после закрытия
    try:
        win.finished.connect(lambda _res: _clear_settings_ref())
    except Exception:
        pass
    win.show(); win.raise_(); win.activateWindow();
    logger.debug('Settings window shown, entering modal loop')
    win.exec_()
    logger.debug('Settings window closed (exec loop ended)')

def _clear_settings_ref():
    global _settings_window_ref
    _settings_window_ref = None