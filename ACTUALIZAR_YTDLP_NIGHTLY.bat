@echo off
chcp 65001 >nul
title LushiTube - Actualizar yt-dlp

echo ========================================================
echo   LushiTube - Actualizacion de compatibilidad YouTube
echo ========================================================
echo.
echo Se instalara la version NIGHTLY de yt-dlp y curl-cffi.
echo.
python -m pip install -U --pre "yt-dlp[default,curl-cffi]"
if errorlevel 1 (
  echo.
  echo [ERROR] No se pudo actualizar yt-dlp.
  pause
  exit /b 1
)
echo.
echo [OK] yt-dlp actualizado. Reinicia LushiTube con: python app.py
pause
