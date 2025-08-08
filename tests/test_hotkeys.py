import os, json, tempfile, uuid, sys, importlib

# We import hotkey_engine after setting env var to override path

def test_hotkeys_load_save_roundtrip(tmp_path):
    test_file = tmp_path / 'hotkeys.json'
    os.environ['HOTKEYMASTER_HOTKEYS_FILE'] = str(test_file)
    if 'hotkey_engine' in sys.modules:
        del sys.modules['hotkey_engine']
    hotkey_engine = importlib.import_module('hotkey_engine')
    # Initially empty
    hk = hotkey_engine.load_hotkeys()
    assert hk == []
    sample = [{'type':'keyboard','combo':{'mods':['Cmd'],'vk':12,'disp':'Cmd + Q'},'action':'run echo','scope':'global','app':'','enabled':True}]
    hotkey_engine.save_hotkeys(sample)
    loaded = hotkey_engine.load_hotkeys()
    assert len(loaded) == 1
    assert loaded[0]['action'] == 'run echo'
    # IDs auto-added
    assert 'id' in loaded[0]


def test_hotkeys_cache_invalidation(tmp_path):
    test_file = tmp_path / 'hotkeys.json'
    os.environ['HOTKEYMASTER_HOTKEYS_FILE'] = str(test_file)
    if 'hotkey_engine' in sys.modules:
        del sys.modules['hotkey_engine']
    hotkey_engine = importlib.import_module('hotkey_engine')
    hotkey_engine.save_hotkeys([])
    assert hotkey_engine.load_hotkeys() == []
    # Direct write to file (simulate external change)
    with open(test_file,'w',encoding='utf-8') as f:
        json.dump([{'type':'trackpad','gesture':'Тап тремя пальцами','action':'open example.com','scope':'global','app':'','enabled':True}], f)
    # Force refresh
    hotkey_engine.refresh_hotkeys_cache(force=True)
    loaded = hotkey_engine.load_hotkeys()
    assert len(loaded) == 1
    assert loaded[0]['type'] == 'trackpad'
