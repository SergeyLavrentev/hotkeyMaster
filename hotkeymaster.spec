# -*- mode: python ; coding: utf-8 -*-

datas = [
    ('hotkeys.json', '.'),
    ('icons/HotkeyMaster.icns', 'icons'),
    ('icons/tray_icon.png', 'icons'),
]

hiddenimports = [
    'PyQt5.QtWidgets',
    'PyQt5.QtCore',
    'PyQt5.QtGui',
    'pynput.keyboard',
    'pystray',
    'PIL.Image',
    'PIL.ImageDraw',
    'Quartz',
    'AppKit',
    'Foundation',
    'objc',
    'pyobjc',
    'pyobjc_framework_AppKit',
    'pyobjc_framework_Quartz',
    'pyobjc_framework_Foundation',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='HotkeyMaster',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icons/HotkeyMaster.icns',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='HotkeyMaster',
)

app = BUNDLE(
    coll,
    name='HotkeyMaster.app',
    icon='icons/HotkeyMaster.icns',
    bundle_identifier='com.rocker.HotkeyMaster',
    info_plist='icons/Info.plist',
)
