@echo off
setlocal
REM ============================================================================
REM  ClassMatch - liga o servidor Flask e abre o site no navegador.
REM  Deixe a janela preta aberta enquanto usa o site.
REM  Para desligar: feche a janela ou aperte Ctrl+C.
REM ============================================================================
cd /d "%~dp0"
REM Aberto de dentro do .zip (sem extrair)? O Windows so copia este arquivo e nada funciona.
if not exist "%~dp0app.py" goto erro_zip
title ClassMatch - servidor

REM Procura o Python do computador (varias pastas + caminho salvo em python_caminho.txt).
call "%~dp0achar_python.bat"

REM Na primeira vez (ou se faltar alguma biblioteca), instala sozinho.
if not defined PY goto instalar
%PY% -c "import sys; sys.path.insert(0, 'bibliotecas'); import flask, pymysql" >nul 2>&1
if errorlevel 1 goto instalar
goto ligar

:instalar
echo.
echo  Falta instalar o backend neste computador. Instalando agora...
call instalar.bat nopause
if errorlevel 1 goto erro_instalar
REM o instalar.bat pode ter achado o Python agora (caminho salvo): procura de novo
call "%~dp0achar_python.bat"

:ligar
%PY% app.py --abrir
echo.
echo  O servidor parou. Se apareceu um ERRO acima, a mensagem diz o que fazer.
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
