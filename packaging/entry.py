"""Точка входа PyInstaller — абсолютный импорт, чтобы собранный exe
стартовал без пакетного контекста (в отличие от `python -m sunthemes`)."""
from sunthemes.app import main

if __name__ == "__main__":
    main()
