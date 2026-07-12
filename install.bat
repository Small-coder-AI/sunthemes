@echo off
chcp 65001 >nul
echo Устанавливаю зависимости...
pip install -r "%~dp0requirements.txt"
echo.
echo Готово. Запуск: run.bat
pause
