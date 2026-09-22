# LushiTube Cloud v4

- Corrige un bug de reintentos: antes solo cambiaba de ruta ante un `HTTP 403` literal. Ahora también reintenta frente a `Sign in to confirm you're not a bot`, errores de sesión, formatos bloqueados y otros rechazos recuperables de YouTube.
- Conserva en `/status/<uid>` el número de intento y la ruta activa durante toda la transferencia.
- Añade rutas de fallback de YouTube y soporte opcional para `YTDLP_PROXY` y `YOUTUBE_COOKIES_B64`.
- `/health` informa versión de yt-dlp, EJS, curl-cffi, PO Token, Node, FFmpeg y si hay proxy/cookies configurados.
- La UI muestra cambio de ruta, etapa, velocidad, ETA, transferencia/procesado y diagnóstico cloud.
- Las nuevas animaciones son funcionales: su velocidad y estado dependen del progreso, de la velocidad real o de los reintentos.
