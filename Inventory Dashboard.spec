"""
PyInstaller spec for Inventory Dashboard EXE
"""
# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import (
    collect_submodules,
    collect_data_files,
    copy_metadata,
)
from glob import glob

# Hidden imports
hiddenimports = []
hiddenimports += collect_submodules('app')
hiddenimports += collect_submodules('streamlit.runtime')
hiddenimports += collect_submodules('streamlit.web')
try:
    hiddenimports += collect_submodules('reportlab')
except Exception:
    pass

# Data files and package metadata
datas = []
datas += copy_metadata('streamlit')
datas += collect_data_files('streamlit')

try:
    datas += copy_metadata('plotly')
    datas += collect_data_files('plotly')
except Exception:
    pass

# Include reportlab package data (fonts, etc.) if available for PDF export
try:
    datas += copy_metadata('reportlab')
    datas += collect_data_files('reportlab')
except Exception:
    pass

# Entry script used by launch_app.py
datas += [('streamlit_app.py', '.')]
# Ship local configuration and JSON templates used by the app
try:
    datas += [('config_local.py', '.')]
except Exception:
    pass
try:
    for f in glob('history/*.json'):
        datas += [(f, 'history')]
except Exception:
    pass

# Include history CSVs if present (e.g., metrics_history.csv)
try:
    for f in glob('history/*.csv'):
        datas += [(f, 'history')]
except Exception:
    pass

a = Analysis(
    ['launch_app.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    name='Inventory Dashboard',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

