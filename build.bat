@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo  Theme Switcher - сборка в .exe
echo ============================================
echo.

echo [1/4] Установка PyInstaller, Pillow и зависимостей...
pip install --upgrade pyinstaller pillow PySide6 astral || goto :error

echo.
echo [2/4] Генерация иконки...
python generate_icon.py || goto :error

echo.
echo [3/4] Очистка старой сборки...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo.
echo [4/4] Сборка .exe из ThemeSwitcher.spec (1-3 минуты)...
REM Используем .spec из репозитория — там настроены excludes (лишние модули PySide6
REM отрезаны, exe ~30-40 МБ вместо ~80) и upx=False (чтобы Defender реже ругался).
pyinstaller --noconfirm ThemeSwitcher.spec || goto :error

echo.
echo ============================================
echo  ГОТОВО
echo ============================================
echo.
echo Файл: %~dp0dist\ThemeSwitcher.exe
echo.
echo Можно скопировать .exe куда угодно — Python для работы не нужен.
echo Первый запуск может занять 3-5 секунд (распаковка во временную папку).
echo.
pause
exit /b 0

:error
echo.
echo !!! ОШИБКА сборки. Смотри вывод выше.
pause
exit /b 1
