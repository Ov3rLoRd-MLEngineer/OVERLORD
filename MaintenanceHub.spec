# -*- mode: python ; coding: utf-8 -*-
# MaintenanceHub.spec -- Ov3rLoRd V1.49q
# Auto-genere par build_exe.py -- NE PAS EDITER MANUELLEMENT

block_cipher = None

a = Analysis(
    ['D:/OVERLORD/aAa_MaintenanceHub.py'],
    pathex=['D:/OVERLORD'],
    binaries=[],
    datas=[
    ('D:/OVERLORD/agents', 'agents'),
    ('D:/OVERLORD/overlord_utils_utf8.py', '.'),
    ('D:/OVERLORD/patcher.py', '.'),
    ('D:/OVERLORD/test_pipeline.py', '.')
],
    hiddenimports=[
    'agents.overlord_utils',
    'agents.context_bus',
    'customtkinter',
    'PIL._tkinter_finder'
],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'IPython', 'jupyter'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='MaintenanceHub',
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
    icon=None,
)
