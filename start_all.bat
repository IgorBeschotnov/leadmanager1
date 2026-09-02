@echo off
cd /d D:\projects\leadmanager1

REM активуємо venv
call .venv\Scripts\activate.bat

REM Django в окремому вікні
start "Django" cmd /k "python manage.py runserver"

REM невелика пауза, щоб Django встиг піднятися
timeout /t 3 /nobreak >nul

REM Бот у цьому ж вікні (або окремому — розкоментуй start)
python bot.py

pause