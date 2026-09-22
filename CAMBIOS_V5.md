# LushiTube Cloud v5

## Qué se corrigió

- YouTube ahora recorre todas las rutas de recuperación para errores de yt-dlp que antes podían quedar clasificados como `download-error` y detenerse en el primer intento.
- Se eliminó `check_formats=selected` de la configuración base de descarga para evitar validaciones previas que pueden fallar en hosts cloud antes de la transferencia real.
- SoundCloud tiene estrategia propia:
  1. stream HTTP/progresivo,
  2. HLS/AAC,
  3. ruta automática de yt-dlp.
- SoundCloud fuerza renovación de información de cliente en el intento inicial de metadata y añade cabeceras de origen/referer.
- MP4 se deshabilita en la vista previa de SoundCloud porque la fuente es de audio; se mantienen MP3 y WAV.
- Mensajes de diagnóstico separados para YouTube y SoundCloud.
- `/health` ahora reporta `youtube_cloud_mode: multi-route-v5` y `soundcloud_cloud_mode: progressive-hls-v5`.

## Antes de subir a GitHub

No es necesario ejecutar los archivos `.bat` ni `start.sh`.

Los `.bat` son utilidades para Windows local. `start.sh` lo ejecuta Render automáticamente dentro del contenedor Docker.

Opcional, solo para validar en tu PC:

```powershell
python -m py_compile app.py
node --check static/js/main.js
```

Después:

```powershell
git add .
git commit -m "fix cloud downloads v5"
git push origin main
```
