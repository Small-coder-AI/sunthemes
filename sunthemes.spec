# -*- mode: python ; coding: utf-8 -*-
# Сборка Sunthemes в автономный onedir-exe (Windows, трей).
# Build:  uv run pyinstaller sunthemes.spec --noconfirm
# Output: dist/Sunthemes/Sunthemes.exe (+ каталог _internal)

a = Analysis(
    ['packaging/entry.py'],
    pathex=['src'],
    binaries=[],
    # icon.ico кладём внутрь пакета sunthemes — его ищет ui.make_app_icon()
    # через importlib.resources.
    datas=[('src/sunthemes/icon.ico', 'sunthemes')],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Sunthemes',
    console=False,            # windowed — консольного окна нет
    icon='src/sunthemes/icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name='Sunthemes',
)
