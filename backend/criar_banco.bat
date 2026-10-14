@echo off
setlocal
REM ============================================================================
REM  ClassMatch - cria (ou recria) o banco classmatch_db rodando o
REM  database\banco.sql. Nao precisa abrir o MySQL Workbench.
REM  ATENCAO: apaga os dados que estiverem no banco e poe os dados de teste.
REM ============================================================================
cd /d "%~dp0"
REM Aberto de dentro do .zip (sem extrair)? O Windows so copia este arquivo e nada funciona.
if not exist "%~dp0app.py" goto erro_zip
title ClassMatch - criar banco

REM Procura o Python do computador (varias pastas + caminho salvo em python_caminho.txt).
call "%~dp0achar_python.bat"

if not defined PY goto instalar
%PY% -c "import sys; sys.path.insert(0, 'bibliotecas'); import flask, pymysql" >nul 2>&1
if errorlevel 1 goto instalar
goto criar

:instalar
echo.
echo  Falta instalar o backend neste computador. Instalando agora...
call instalar.bat nopause
if errorlevel 1 goto erro_instalar
call "%~dp0achar_python.bat"

:criar
%PY% app.py --criar-banco
echo.
pause
exit /b 0

:erro_zip
echo.
echo  ERRO: parece que voce abriu este arquivo de DENTRO do .zip.
echo  Clique com o botao direito no .zip, escolha "Extrair tudo" e abra o
echo  backend\iniciar.bat da pasta extraida.
echo.
pause
exit /b 1

:erro_instalar
echo.
echo  A instalacao nao terminou. Leia a mensagem de ERRO acima.
echo.
pause
exit /b 1
