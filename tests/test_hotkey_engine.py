import unittest
import tempfile
import os
import sys
import json
import types
from unittest import mock

class HotkeyEngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # temporary HOME so App Support path goes to temp dir
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.env_patch = mock.patch.dict(os.environ, {"HOME": cls.tmpdir.name})
        cls.env_patch.start()
        # stub Quartz and PyQt5 before importing module
        quartz_stub = types.SimpleNamespace(
            CGEventCreateKeyboardEvent=lambda *a, **k: object(),
            CGEventSetFlags=lambda *a, **k: None,
            CGEventPost=lambda *a, **k: None,
            CGMainDisplayID=lambda: 1,
            kCGHIDEventTap=0,
            kCGEventFlagMaskCommand=1,
            kCGEventFlagMaskShift=2,
            kCGEventFlagMaskAlternate=4,
            kCGEventFlagMaskControl=8,
            CGEventMaskBit=lambda x: 1,
            kCGEventKeyDown=1,
            CGWindowListCopyWindowInfo=lambda *a, **k: [],
            kCGWindowListOptionOnScreenOnly=0,
            kCGNullWindowID=0
        )
        cls.quartz_patch = mock.patch.dict(sys.modules, {"Quartz": quartz_stub})
        cls.quartz_patch.start()
        qt_stub = types.SimpleNamespace()
        cls.qt_patch = mock.patch.dict(sys.modules, {
            "PyQt5": types.SimpleNamespace(QtWidgets=qt_stub),
            "PyQt5.QtWidgets": qt_stub
        })
        cls.qt_patch.start()
        import importlib
        cls.he = importlib.import_module("hotkey_engine")
        # provide missing brightness functions
        cls.he.get_display_brightness = lambda: 0.5
        cls.he.set_display_brightness = lambda v: None

    @classmethod
    def tearDownClass(cls):
        cls.env_patch.stop()
        cls.quartz_patch.stop()
        cls.qt_patch.stop()
        cls.tmpdir.cleanup()

    def test_parse_combo(self):
        mods, vk = self.he.parse_combo({"mods": ["Cmd", "Shift"], "vk": 12})
        self.assertEqual(mods, frozenset({"Cmd", "Shift"}))
        self.assertEqual(vk, 12)

    def test_get_hotkey_key_keyboard(self):
        hk = {
            "type": "keyboard",
            "combo": {"mods": ["Cmd"], "vk": 1},
            "scope": "app",
            "app": "Chrome"
        }
        key = self.he.get_hotkey_key(hk)
        self.assertEqual(key, ("keyboard", 1, frozenset({"Cmd"}), "app", "Chrome"))

    def test_get_hotkey_key_trackpad(self):
        hk = {"type": "trackpad", "gesture": "tap", "scope": "global", "app": ""}
        key = self.he.get_hotkey_key(hk)
        self.assertEqual(key, ("trackpad", "tap", "global", ""))

    def test_save_and_load_hotkeys(self):
        data = [{"type": "keyboard", "combo": {"mods": [], "vk": 10}}]
        self.he.save_hotkeys(data)
        loaded = self.he.load_hotkeys()
        self.assertEqual(loaded, data)

    def test_run_action_open(self):
        with mock.patch("webbrowser.open") as wopen:
            self.he.run_action("open example.com")
            wopen.assert_called_with("https://example.com")

    def test_run_action_run(self):
        with mock.patch("hotkey_engine.subprocess.Popen") as popen:
            self.he.run_action("run echo 1")
            popen.assert_called_with("echo 1", shell=True)

    def test_run_action_hotkey(self):
        combo = json.dumps({"mods": ["Cmd"], "vk": 3})
        with mock.patch("hotkey_engine.CGEventCreateKeyboardEvent", return_value="ev") as create, \
             mock.patch("hotkey_engine.CGEventSetFlags") as setf, \
             mock.patch("hotkey_engine.CGEventPost") as post:
            self.he.run_action(f"hotkey:{combo}")
            self.assertEqual(create.call_count, 2)
            post.assert_called_with(self.he.kCGHIDEventTap, "ev")

    def test_run_action_brightness_set_with_helper(self):
        with mock.patch("hotkey_engine.os.path.exists", return_value=True), \
             mock.patch("hotkey_engine.os.access", return_value=True), \
             mock.patch("hotkey_engine.subprocess.run") as srun:
            self.he.run_action("brightness_set 50")
            srun.assert_called_with([self.he.helper_path, "0.5"], check=True, capture_output=True, text=True)

    def test_run_action_brightness_up_down(self):
        with mock.patch("hotkey_engine.get_display_brightness", return_value=0.4), \
             mock.patch("hotkey_engine.os.path.exists", return_value=False), \
             mock.patch("hotkey_engine.CoreDisplay_Display_SetUserBrightness", None), \
             mock.patch("hotkey_engine.set_display_brightness") as sset:
            self.he.run_action("brightness_up")
            sset.assert_called_with(0.5)
        with mock.patch("hotkey_engine.get_display_brightness", return_value=0.6), \
             mock.patch("hotkey_engine.os.path.exists", return_value=False), \
             mock.patch("hotkey_engine.CoreDisplay_Display_SetUserBrightness", None), \
             mock.patch("hotkey_engine.set_display_brightness") as sset:
            self.he.run_action("brightness_down")
            sset.assert_called_with(0.5)

if __name__ == "__main__":
    unittest.main()
