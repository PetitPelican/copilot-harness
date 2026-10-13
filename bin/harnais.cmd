@echo off
rem LE LANCEUR WINDOWS - `harnais <sous-commande>` tape par un agent ou une fiche.
rem
rem Meme recherche que bin/harnais (sh), dans la langue de cmd :
rem   1. HARNAIS_PYTHON s'il est pose, et lui seul (les essais) ;
rem   2. `py` (le lanceur de Windows : `py -3`) - jamais filtre, le faux Python
rem      du Microsoft Store ne s'appelle pas `py` ;
rem   3. `python`, puis `python3`, HORS WindowsApps : le relais du Store ouvre
rem      le Store au lieu d'executer.
rem Pas de bloc entre parentheses autour d'un chemin : un dossier
rem "C:\Users\Jean (Pro)" casserait la lecture du fichier par cmd.
rem Un Python absent se DIT, avec le code du hook : 2 pour les gardes, 1 sinon.
setlocal
set "RACINE=%~dp0.."
set "CODE=1"
if /i "%~1"=="mind-guard" set "CODE=2"
if /i "%~1"=="perimetre" set "CODE=2"
if not exist "%RACINE%\py\main.py" goto :sans_paquet
if not defined COPILOT_PLUGIN_ROOT set "COPILOT_PLUGIN_ROOT=%RACINE%"
set "MAISON=%COPILOT_HOME%"
if not defined MAISON set "MAISON=%USERPROFILE%\.copilot"
set "DONNEES=%COPILOT_PLUGIN_DATA%"
if not defined DONNEES set "DONNEES=%PLUGIN_DATA%"
if not defined DONNEES set "DONNEES=%MAISON%\plugin-data\atelier-copilot\harnais"
set "PY="
if defined HARNAIS_PYTHON goto :impose
for /f "delims=" %%p in ('where py 2^>nul') do if not defined PY set "PY=%%p"
if defined PY goto :lanceur
for /f "delims=" %%p in ('where python 2^>nul ^| findstr /v /i "WindowsApps"') do if not defined PY set "PY=%%p"
if defined PY goto :direct
for /f "delims=" %%p in ('where python3 2^>nul ^| findstr /v /i "WindowsApps"') do if not defined PY set "PY=%%p"
if defined PY goto :direct
goto :sans_python

:impose
if not exist "%HARNAIS_PYTHON%" goto :sans_python
set "PY=%HARNAIS_PYTHON%"
goto :direct

:lanceur
"%PY%" -3 -S -E -X "pycache_prefix=%DONNEES%\pycache" "%RACINE%\py\main.py" %*
exit /b %ERRORLEVEL%

:direct
"%PY%" -S -E -X "pycache_prefix=%DONNEES%\pycache" "%RACINE%\py\main.py" %*
exit /b %ERRORLEVEL%

:sans_paquet
echo harnais : le programme du paquet manque dans %RACINE%\py - remettre le paquet en etat : copilot plugin update harnais@atelier-copilot 1>&2
exit /b %CODE%

:sans_python
echo harnais : aucun Python 3.9 ou plus n'est installe sur cette machine - les gardes du paquet ne partent pas, rien ne les remplace. Installer Python (winget install Python.Python.3.13, ou python.org en cochant "Add to PATH"), puis relancer l'agent. Le faux python du Microsoft Store ne compte pas. 1>&2
exit /b %CODE%
