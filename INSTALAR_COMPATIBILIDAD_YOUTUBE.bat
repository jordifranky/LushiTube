@echo off
setlocal
chcp 65001 >nul
title LushiTube - Compatibilidad YouTube PO Token

echo ========================================================
echo   LushiTube - Compatibilidad avanzada para YouTube
echo ========================================================
echo.
echo Este instalador prepara el proveedor local de PO Token recomendado
 echo por la documentacion actual de yt-dlp para videos que responden 403.
echo.

where git >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Git no esta instalado o no esta en PATH.
  echo Instala Git for Windows y vuelve a ejecutar este archivo.
  pause
  exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
  echo [ERROR] npm no esta disponible. Node.js debe incluir npm.
  pause
  exit /b 1
)

echo [1/4] Actualizando yt-dlp y el plugin de PO Token...
python -m pip install -U --pre "yt-dlp[default,curl-cffi]" bgutil-ytdlp-pot-provider
if errorlevel 1 goto :fail

set "POT_HOME=%USERPROFILE%\bgutil-ytdlp-pot-provider"
if not exist "%POT_HOME%\.git" (
  echo [2/4] Descargando proveedor oficial/comunitario bgutil...
  git clone --depth 1 https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git "%POT_HOME%"
  if errorlevel 1 goto :fail
) else (
  echo [2/4] Actualizando proveedor existente...
  git -C "%POT_HOME%" pull --ff-only
  if errorlevel 1 goto :fail
)

echo [3/4] Instalando dependencias Node del proveedor...
pushd "%POT_HOME%\server"
call npm ci
if errorlevel 1 (
  popd
  goto :fail
)

echo [4/4] Compilando proveedor...
call npx tsc
if errorlevel 1 (
  popd
  goto :fail
)
popd

echo.
echo ========================================================
echo [OK] Compatibilidad avanzada instalada.
echo Cierra LushiTube si esta abierto y ejecuta de nuevo: python app.py
echo ========================================================
pause
exit /b 0

:fail
echo.
echo [ERROR] La instalacion no termino correctamente.
echo Revisa el mensaje anterior y vuelve a intentarlo.
pause
exit /b 1
