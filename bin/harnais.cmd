@echo off
setlocal
set "ROOT=%~dp0"
set "BIN=%ROOT%harnais-windows-x86_64.exe"
if exist "%BIN%" (
  "%BIN%" %*
  goto :result
)
echo harnais : le programme du paquet manque dans %ROOT% ^(attendu : harnais-windows-x86_64.exe^). 1>&2
echo remettre le paquet en etat : copilot plugin update harnais@atelier-copilot 1>&2
exit /b 127
:result
exit /b %ERRORLEVEL%
