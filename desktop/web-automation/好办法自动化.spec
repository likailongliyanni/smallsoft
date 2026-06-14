# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('D:\\project\\0527-tools\\software_v2\\app\\inject.js', 'app'), ('D:\\project\\0527-tools\\software_v2\\app\\stealth.js', 'app'), ('C:\\Users\\T14\\AppData\\Local\\Programs\\Python\\Python314\\Lib\\site-packages\\customtkinter', 'customtkinter'), ('D:\\project\\0527-tools\\software_v2\\app\\pay_qr.png', 'app'), ('C:\\Users\\T14\\AppData\\Local\\Programs\\Python\\Python314\\Lib\\site-packages\\playwright\\driver', 'playwright/driver')]
binaries = []
hiddenimports = ['customtkinter', 'playwright', 'playwright.sync_api', 'playwright._impl', 'playwright._impl._driver', 'requests', 'urllib3', 'certifi', 'openpyxl', 'et_xmlfile', 'PIL', 'PIL.Image', 'PIL.ImageDraw', 'PIL.ImageFilter']
tmp_ret = collect_all('charset_normalizer')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('idna')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('openpyxl')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('PIL')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['D:\\project\\0527-tools\\software_v2\\main.py'],
    pathex=[],
    binaries=binaries,
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
    [],
    exclude_binaries=True,
    name='好办法自动化',
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
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='好办法自动化',
)
