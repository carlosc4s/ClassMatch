@echo off
REM ============================================================================
REM  ClassMatch - descobre o Python do computador e guarda o comando em PY.
REM  Usado pelo instalar.bat, iniciar.bat e criar_banco.bat.
REM  Se o Python estiver num lugar diferente, o instalar.bat pergunta o caminho
REM  e guarda em backend\python_caminho.txt (lido aqui nas proximas vezes).
REM ============================================================================
set "PY="
set "PY_SALVO="
if exist "%~dp0python_caminho.txt" set /p PY_SALVO=<"%~dp0python_caminho.txt"
if defined PY_SALVO call :testar "%PY_SALVO%"
if not defined PY py -3 -c "import sys" >nul 2>&1 && set "PY=py -3"
if not defined PY python -c "import sys" >nul 2>&1 && set "PY=python"
if not defined PY python3 -c "import sys" >nul 2>&1 && set "PY=python3"
for %%B in ("%ProgramFiles%" "%ProgramFiles(x86)%" "%LOCALAPPDATA%\Programs\Python" "C:") do (
    if not defined PY for /d %%D in ("%%~B\Python3*") do if not defined PY call :testar "%%~D\python.exe"
)
REM Python instalado pelo novo "Python install manager" do python.org
for /d %%D in ("%LOCALAPPDATA%\Python\pythoncore-3*") do if not defined PY call :testar "%%~D\python.exe"
for %%D in ("%USERPROFILE%\anaconda3" "%USERPROFILE%\miniconda3" "%ProgramData%\anaconda3" "%ProgramData%\miniconda3" "%LOCALAPPDATA%\anaconda3") do (
    if not defined PY call :testar "%%~D\python.exe"
)
goto :eof

:testar
if not exist "%~1" goto :eof
"%~1" -c "import sys" >nul 2>&1 && set "PY="%~1""
goto :eof
