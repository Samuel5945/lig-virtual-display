# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[('backend.py', '.'), ('../vdd_core.py', '.'), ('../gui/app.ico', '.'), ('../driver/MttVDD.inf', 'driver'), ('../driver/MttVDD.dll', 'driver'), ('../driver/MttVDD.cat', 'driver'), ('../driver/devcon.exe', 'driver'), ('../driver/vdd_settings.xml', 'driver')],
    hiddenimports=['backend', 'vdd_core', 'json', 'xml', 'xml.etree', 'xml.etree.ElementTree', 'ctypes', 'ctypes.wintypes'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='VirtualDisplayPanel',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['..\\gui\\app.ico'],
)
