@echo off
title ClassMatch - teste de e-mail
cd /d "%~dp0"
REM Manda um e-mail de teste para conferir EMAIL_USUARIO e EMAIL_SENHA_APP do .env
call "%~dp0achar_python.bat"
if not defined PY goto sem_python
%PY% app.py --testar-email
echo.
pause
exit /b 0

:sem_python
echo.
echo  Nao achei o Python. Rode o instalar.bat antes.
echo.
pause
exit /b 1
