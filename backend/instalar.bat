@echo off
setlocal
REM ============================================================================
REM  ClassMatch - instala as bibliotecas do backend (Flask, PyMySQL, cryptography)
REM
REM  As bibliotecas ficam na pasta backend\bibliotecas e o app.py carrega de la.
REM  NAO usamos venv: em computador de escola o Windows costuma bloquear o
REM  python.exe copiado para dentro do venv - erro "WinError 1260, politica
REM  de grupo". Assim, so roda o Python oficial, que o Windows permite.
REM
REM  Pode rodar quantas vezes quiser. O iniciar.bat chama este arquivo sozinho.
REM ============================================================================
cd /d "%~dp0"
title ClassMatch - instalacao

echo.
echo  ClassMatch - instalacao do backend
echo  ------------------------------------------------

REM Procura o Python do computador (varias pastas + caminho salvo em python_caminho.txt).
call "%~dp0achar_python.bat"
if not defined PY goto erro_sem_python
:achou_python
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
if errorlevel 1 goto erro_python_velho
%PY% -c "import sys; print('  [1/3] Python', sys.version.split()[0], 'em', sys.executable)"

REM A pasta venv da versao antiga nao e mais usada.
if exist venv rmdir /s /q venv >nul 2>&1

REM O pip vem junto com o Python; se faltar, tenta instalar.
%PY% -m pip --version >nul 2>&1
if not errorlevel 1 goto instalar_pacotes
echo  O pip nao esta instalado neste Python. Tentando instalar...
%PY% -m ensurepip --user >nul 2>&1
%PY% -m pip --version >nul 2>&1
if errorlevel 1 goto erro_sem_pip

:instalar_pacotes
echo  [2/3] Baixando as bibliotecas para backend\bibliotecas - precisa de internet...
%PY% -m pip install -r requirements.txt --target bibliotecas --upgrade --disable-pip-version-check --no-warn-script-location
if errorlevel 1 goto erro_pip

echo  [3/3] Conferindo...
%PY% -c "import sys; sys.path.insert(0, 'bibliotecas'); import flask, pymysql"
if errorlevel 1 goto erro_pip
%PY% -c "import sys; sys.path.insert(0, 'bibliotecas'); from cryptography.hazmat.primitives.asymmetric import rsa" >nul 2>&1
if errorlevel 1 goto aviso_cryptography
goto concluido

:aviso_cryptography
echo.
echo  AVISO: o Windows bloqueou a biblioteca "cryptography".
echo  Quase sempre o ClassMatch funciona mesmo assim. So se o servidor
echo  reclamar de "cryptography" ao conectar no MySQL, veja a parte
echo  "Computador da escola" no README.md.

:concluido
echo.
echo  ================================================
echo   Instalacao concluida!
echo   Agora de dois cliques em iniciar.bat
echo  ================================================
echo.
if /i not "%~1"=="nopause" pause
exit /b 0

REM ---- Mensagens de erro -----------------------------------------------------
:erro_sem_python
echo.
echo  Nao achei o Python sozinho neste computador.
echo.
echo  SE O PYTHON ESTA INSTALADO: no menu Iniciar, procure "python", clique com o
echo  botao direito em "Python 3.x" e em "Abrir local do arquivo" (repita ate ver o
echo  python.exe). Segure Shift, clique com o botao direito no python.exe, escolha
echo  "Copiar como caminho" e cole aqui embaixo (botao direito cola no terminal).
echo.
echo  SE NAO ESTA INSTALADO: so aperte Enter para ver como instalar.
echo.
set "CAMINHO="
set /p "CAMINHO=  Caminho do python.exe: "
if not defined CAMINHO goto sem_python
set "CAMINHO=%CAMINHO:"=%"
if exist "%CAMINHO%\python.exe" set "CAMINHO=%CAMINHO%\python.exe"
if not exist "%CAMINHO%" goto caminho_invalido
"%CAMINHO%" -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
if errorlevel 1 goto caminho_invalido
>"%~dp0python_caminho.txt" echo %CAMINHO%
set "PY="%CAMINHO%""
echo  Achei! Guardei o caminho em backend\python_caminho.txt para as proximas vezes.
goto achou_python

:caminho_invalido
echo.
echo  Esse caminho nao e de um python.exe que funciona (precisa ser Python 3.8 ou mais novo).
goto erro_sem_python

:sem_python
echo.
echo  COMO INSTALAR: baixe em https://www.python.org/downloads/
echo  e MARQUE a opcao "Add python.exe to PATH" na primeira tela do instalador.
echo  Nao precisa ser administrador: deixe desmarcado "Use admin privileges".
echo  Em computador da escola, se bloquear, peca para o tecnico instalar o Python.
echo  Depois de instalar, feche esta janela e abra o iniciar.bat de novo.
echo.
pause
exit /b 1

:erro_python_velho
echo.
echo  ERRO: o Python encontrado e muito antigo. O ClassMatch precisa do 3.8 ou mais novo.
echo  Instale a versao atual em https://www.python.org/downloads/
echo.
pause
exit /b 1

:erro_sem_pip
echo.
echo  ERRO: este Python veio sem o pip, que baixa as bibliotecas.
echo  Reinstale o Python marcando a opcao "pip" - ou peca para o tecnico da escola.
echo.
pause
exit /b 1

:erro_pip
echo.
echo  ERRO: a instalacao das bibliotecas falhou - leia a mensagem acima.
echo  Causa mais comum: sem internet, ou a rede da escola bloqueia o pip.
echo  Tente em outra rede, por exemplo o roteador do celular, e rode de novo.
echo  Outra saida: instale em casa e traga a pasta backend\bibliotecas no pendrive.
echo.
pause
exit /b 1
