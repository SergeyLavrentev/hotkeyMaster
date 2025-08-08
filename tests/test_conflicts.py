import os
import json
import importlib

def setup_engine(tmp_path):
    os.environ['HOTKEYMASTER_HOTKEYS_FILE'] = str(tmp_path / 'hotkeys.json')
    # Ensure empty file
    with open(os.environ['HOTKEYMASTER_HOTKEYS_FILE'], 'w', encoding='utf-8') as f:
        json.dump([], f)
    import sys
    sys.modules.pop('hotkey_engine', None)
    import hotkey_engine
    importlib.reload(hotkey_engine)
    return hotkey_engine

def test_keyboard_conflict_strict(tmp_path):
    eng = setup_engine(tmp_path)
    base = {
        'id': 'a',
        'type': 'keyboard',
        'combo': {'mods': ['Cmd','Shift'], 'vk': 12, 'disp': 'Cmd + Shift + Q'},
        'action': 'run echo 1',
        'scope': 'global',
        'app': '',
        'enabled': True
    }
    conflict_same = {
        'type': 'keyboard',
        'combo': {'mods': ['Shift','Cmd'], 'vk': 12, 'disp': 'Cmd + Shift + Q'},
        'action': 'run echo 2',
        'scope': 'global',
        'app': '',
        'enabled': True
    }
    no_conflict_different_vk = {
        'type': 'keyboard',
        'combo': {'mods': ['Cmd','Shift'], 'vk': 13, 'disp': 'Cmd + Shift + W'},
        'action': 'run echo 3',
        'scope': 'global',
        'app': '',
        'enabled': True
    }
    res1 = eng.hotkey_conflicts(conflict_same, [base], strict=True)
    assert res1 is not None, 'Ожидаем конфликт при одинаковом vk и модификаторах в strict режиме'
    res2 = eng.hotkey_conflicts(no_conflict_different_vk, [base], strict=True)
    assert res2 is None, 'Не ожидаем конфликт при другом vk'

def test_keyboard_conflict_subset_non_strict(tmp_path):
    eng = setup_engine(tmp_path)
    base = {
        'id': 'a', 'type':'keyboard', 'combo': {'mods':['Cmd'], 'vk': 12, 'disp':'Cmd + Q'}, 'action':'run 1','scope':'global','app':'','enabled':True
    }
    superset = {
        'type':'keyboard', 'combo': {'mods':['Cmd','Shift'], 'vk':12, 'disp':'Cmd + Shift + Q'}, 'action':'run 2','scope':'global','app':'','enabled':True
    }
    # non-strict: subset or superset should conflict
    res = eng.hotkey_conflicts(superset, [base], strict=False)
    assert res is not None, 'Ожидаем конфликт superset в нестрогом режиме'

def test_trackpad_conflict(tmp_path):
    eng = setup_engine(tmp_path)
    gesture = {
        'id': 'g1','type':'trackpad','combo':None,'gesture':'Тап двумя пальцами','action':'run 1','scope':'global','app':'','enabled':True
    }
    new_same = {
        'type':'trackpad','combo':None,'gesture':'Тап двумя пальцами','action':'run 2','scope':'global','app':'','enabled':True
    }
    res = eng.hotkey_conflicts(new_same, [gesture], strict=True)
    assert res is not None, 'Ожидаем конфликт одинакового жеста'

def test_no_conflict_different_scope_app(tmp_path):
    eng = setup_engine(tmp_path)
    base_app = {
        'id':'x','type':'keyboard','combo': {'mods':['Cmd'], 'vk':15, 'disp':'Cmd + R'}, 'action':'run 1','scope':'app','app':'Safari','enabled':True
    }
    same_combo_other_app = {
        'type':'keyboard','combo': {'mods':['Cmd'], 'vk':15, 'disp':'Cmd + R'}, 'action':'run 2','scope':'app','app':'Xcode','enabled':True
    }
    res = eng.hotkey_conflicts(same_combo_other_app, [base_app], strict=True)
    assert res is None, 'Не ожидаем конфликт для разных приложений при app scope'
