import time
import importlib, sys, os, json

def reload_engine(tmp_path):
    os.environ['HOTKEYMASTER_HOTKEYS_FILE'] = str(tmp_path / 'hotkeys.json')
    with open(os.environ['HOTKEYMASTER_HOTKEYS_FILE'], 'w', encoding='utf-8') as f:
        json.dump([], f)
    sys.modules.pop('hotkey_engine', None)
    import hotkey_engine
    importlib.reload(hotkey_engine)
    return hotkey_engine

def test_keyboard_debounce(tmp_path):
    eng = reload_engine(tmp_path)
    hk = {'id':'abc','type':'keyboard','combo':{'mods':['Cmd'], 'vk':12,'disp':'Cmd + Q'},'scope':'global','app':'','action':'run echo 1'}
    # Первое срабатывание
    assert eng.allow_hotkey_fire(hk) is True
    # Сразу повтор - должен быть подавлен
    assert eng.allow_hotkey_fire(hk) is False
    # По истечении интервала — снова True
    time.sleep(eng.KEY_REPEAT_DEBOUNCE + 0.1)
    assert eng.allow_hotkey_fire(hk) is True
