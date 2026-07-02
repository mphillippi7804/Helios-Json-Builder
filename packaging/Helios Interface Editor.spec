# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\Elite\\Desktop\\Helios Interface Editor\\app\\Helios Interface Editor.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Users\\Elite\\Desktop\\Helios Interface Editor\\app\\assets\\Helios Interface Editor.ico', '.')],
    hiddenimports=[],
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
    [],
    exclude_binaries=True,
    name='Helios Interface Editor',
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
    icon=['C:\\Users\\Elite\\Desktop\\Helios Interface Editor\\app\\assets\\Helios Interface Editor.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Helios Interface Editor',
)
