# -*- mode: python ; coding: utf-8 -*-
# MaestroProduction.spec -- Ov3rLoRd V1.49q
# Auto-genere par build_exe.py -- NE PAS EDITER MANUELLEMENT

block_cipher = None

a = Analysis(
    ['D:/OVERLORD/launcher.py'],
    pathex=['D:/OVERLORD'],
    binaries=[],
    datas=[
    ('D:/OVERLORD/agents', 'agents'),
    ('D:/OVERLORD/overlord_utils_utf8.py', '.'),
    ('D:/OVERLORD/maestro.py', '.'),
    ('D:/OVERLORD/Combined_V35_API.json', '.'),
    ('D:/OVERLORD/node_catalog.json', '.'),
    ('D:/OVERLORD/config.json', '.')
],
    hiddenimports=[
    'agents.overlord_utils',
    'agents.context_bus',
    'agents.director',
    'agents.sourcing',
    'agents.scenario',
    'agents.storyboard',
    'agents.postprod',
    'agents.critic',
    'agents.watchdog',
    'agents.checkpoint_manager',
    'agents.pipeline_conscience',
    'agents.v130_emotion_engine',
    'agents.v130_world_model',
    'agents.v130_generative_world',
    'agents.roles_registry',
    'agents.cost_tracker',
    'agents.narrative_memory',
    'PIL._tkinter_finder',
    'customtkinter'
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
    name='MaestroProduction',
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
