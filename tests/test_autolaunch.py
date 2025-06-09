import unittest
import os
import tempfile
import types
from unittest import mock

class AutoLaunchTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.patch_dir = mock.patch.object(__import__('autolaunch').AutoLaunchManager, 'LAUNCH_AGENTS_DIR', self.tmpdir.name)
        self.patch_dir.start()
        import importlib
        self.al = importlib.reload(__import__('autolaunch'))
        self.patch_plist = mock.patch.object(self.al.AutoLaunchManager, 'PLIST_PATH', os.path.join(self.tmpdir.name, 'com.slavrentev.hotkeymaster.plist'))
        self.patch_plist.start()

    def tearDown(self):
        self.patch_plist.stop()
        self.patch_dir.stop()
        self.tmpdir.cleanup()

    def test_get_plist_content_includes_exec(self):
        content = self.al.AutoLaunchManager.get_plist_content(exec_path='/tmp/app')
        self.assertIn('/tmp/app', content)

    def test_find_preferred_executable(self):
        with mock.patch('glob.glob', return_value=[os.path.join(self.tmpdir.name, 'HotkeyMaster.app')]), \
             mock.patch('os.path.exists', return_value=True):
            path = self.al.AutoLaunchManager.find_preferred_executable()
            self.assertTrue(path.endswith('.app'))

    def test_enable_disable_autolaunch(self):
        with mock.patch.object(self.al.AutoLaunchManager, 'find_preferred_executable', return_value='/bin/app'), \
             mock.patch('subprocess.run') as srun:
            self.al.AutoLaunchManager.enable_autolaunch()
            self.assertTrue(os.path.exists(self.al.AutoLaunchManager.PLIST_PATH))
            srun.assert_called()
            self.al.AutoLaunchManager.disable_autolaunch()
            self.assertFalse(os.path.exists(self.al.AutoLaunchManager.PLIST_PATH))

if __name__ == '__main__':
    unittest.main()
