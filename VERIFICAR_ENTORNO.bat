@echo off
chcp 65001 >nul
echo ========================================
echo  LushiTube - verificacion del entorno
echo ========================================
py -m pip install -U -r requirements.txt

echo.
echo [FFmpeg]
where ffmpeg >nul 2>nul && (ffmpeg -version | findstr /B "ffmpeg version") || echo NO DETECTADO - instala FFmpeg y agrega su carpeta bin al PATH.

echo.
echo [Deno]
where deno >nul 2>nul && (deno --version) || echo No detectado. Recomendado: Deno 2.3 o superior.

echo.
echo [Node.js]
where node >nul 2>nul && (node --version) || echo No detectado. Alternativa: Node.js 22 o superior.

echo.
echo Si no tienes Deno ni Node 22+, YouTube puede devolver HTTP 403.
pause
