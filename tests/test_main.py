import unittest
import sys
import os
import types
import tempfile
from unittest import mock


def worker_is_another_instance(q, home):
    """Helper process to test single-instance logic.

    This function must be defined at module level so that the multiprocessing
    "spawn" start method on macOS can pickle it correctly.
    """
    import importlib
    os.environ['HOME'] = home
    qt_widgets = types.SimpleNamespace(QSystemTrayIcon=object, QMenu=object, QAction=object)
    qt_gui = types.SimpleNamespace(QIcon=object)
    qt_core = types.SimpleNamespace(QObject=object, pyqtSignal=lambda *a, **k: None, Qt=object, QCoreApplication=object)
    sys.modules.update({
        'PyQt5': types.SimpleNamespace(QtWidgets=qt_widgets, QtGui=qt_gui, QtCore=qt_core),
        'PyQt5.QtWidgets': qt_widgets,
        'PyQt5.QtGui': qt_gui,
        'PyQt5.QtCore': qt_core,
        'sip': types.SimpleNamespace(),
        'ui': types.SimpleNamespace(show_settings_window=lambda *a, **k: None),
        'trackpad_engine': types.SimpleNamespace(TrackpadGestureEngine=object),
        'Foundation': types.SimpleNamespace(NSObject=object, NSNotificationCenter=object, NSWorkspace=object),
        'sleep_wake_monitor': types.SimpleNamespace(
            get_sleep_wake_monitor=lambda: types.SimpleNamespace(
                add_sleep_callback=lambda *a, **k: None,
                add_wake_callback=lambda *a, **k: None,
                start_monitoring=lambda *a, **k: None,
                stop_monitoring=lambda *a, **k: None,
            )
        ),
        'Quartz': types.SimpleNamespace(),
    })
    m = importlib.import_module('main')
    q.put(m.is_another_instance_running())

class MainHelpersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.env_patch = mock.patch.dict(os.environ, {"HOME": cls.tmpdir.name})
        cls.env_patch.start()
        quartz_stub = types.SimpleNamespace(
            CGEventCreateKeyboardEvent=lambda *a, **k: None,
            CGEventSetFlags=lambda *a, **k: None,
            CGEventPost=lambda *a, **k: None,
            CGMainDisplayID=lambda: 1,
            kCGHIDEventTap=0,
            kCGEventFlagMaskCommand=1,
            kCGEventFlagMaskShift=2,
            kCGEventFlagMaskAlternate=4,
            kCGEventFlagMaskControl=8,
            CGWindowListCopyWindowInfo=lambda *a, **k: [],
            kCGWindowListOptionOnScreenOnly=0,
            kCGNullWindowID=0
        )
        qt_widgets = types.SimpleNamespace(QSystemTrayIcon=object, QMenu=object, QAction=object)
        qt_gui = types.SimpleNamespace(QIcon=object)
        qt_core = types.SimpleNamespace(QObject=object, pyqtSignal=lambda *a, **k: None, Qt=object, QCoreApplication=object)
        pyqt_stub = types.SimpleNamespace(QtWidgets=qt_widgets, QtGui=qt_gui, QtCore=qt_core)
        trackpad_stub = types.SimpleNamespace(TrackpadGestureEngine=object)
        cls.quartz_patch = mock.patch.dict(sys.modules, {
            "Quartz": quartz_stub,
            "PyQt5": pyqt_stub,
            "PyQt5.QtWidgets": qt_widgets,
            "PyQt5.QtGui": qt_gui,
            "PyQt5.QtCore": qt_core,
            "sip": types.SimpleNamespace(),
            "ui": types.SimpleNamespace(show_settings_window=lambda *a, **k: None),
            "trackpad_engine": trackpad_stub,
            "Foundation": types.SimpleNamespace(NSObject=object, NSNotificationCenter=object, NSWorkspace=object),
            "sleep_wake_monitor": types.SimpleNamespace(get_sleep_wake_monitor=lambda: types.SimpleNamespace(add_sleep_callback=lambda *a, **k: None, add_wake_callback=lambda *a, **k: None, start_monitoring=lambda *a, **k: None, stop_monitoring=lambda *a, **k: None)),
            "objc": types.SimpleNamespace(selector=lambda *a, **k: None),
            "AppKit": types.SimpleNamespace(NSApp=types.SimpleNamespace(setActivationPolicy_=lambda *a, **k: None, activateIgnoringOtherApps_=lambda *a, **k: None), NSApplicationActivationPolicyAccessory=0, NSApplicationActivationPolicyRegular=0)
        })
        cls.quartz_patch.start()
        import importlib
        cls.main = importlib.import_module("main")

    @classmethod
    def tearDownClass(cls):
        cls.env_patch.stop()
        cls.quartz_patch.stop()
        cls.tmpdir.cleanup()

    def test_load_general_settings_default(self):
        self.assertEqual(self.main.load_general_settings(), {"autostart": False})

    def test_load_general_settings_file(self):
        path = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "HotkeyMaster", "settings.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("{\"autostart\": true}")
        self.assertEqual(self.main.load_general_settings(), {"autostart": True})

    def test_is_another_instance_running(self):
        # first call should create lock and return False
        self.assertFalse(self.main.is_another_instance_running())
        # second process should detect lock
        import multiprocessing
        q = multiprocessing.Queue()
        p = multiprocessing.Process(target=worker_is_another_instance, args=(q, os.environ['HOME']))
        p.start(); p.join()
        self.assertTrue(q.get())

if __name__ == "__main__":
    unittest.main()
