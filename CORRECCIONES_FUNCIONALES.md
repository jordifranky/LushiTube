# Correcciones funcionales

- YouTube en Render: yt-dlp nightly + Node 22 + bgutil PO Token Provider en el mismo contenedor.
- YouTube prioriza mweb + PO Token y conserva fallbacks HLS/compatibilidad.
- `/info` también usa PO Token cuando está disponible.
- `/health` confirma FFmpeg, FFprobe, runtime JS y proveedor PO Token.
- Audio → MP3: selector exclusivo de audio y soporte ampliado a MP3, WAV, FLAC, AAC, M4A, OGG/OGA, OPUS, WMA, AIFF/AIF, AC3, AMR, MP2 y MKA.
- El backend valida con FFprobe que exista una pista de audio real.
- Video → MP4: soporte ampliado y validación de pista de video real.

## Despliegue en Render

1. Sustituye los archivos del repositorio por esta versión.
2. Haz commit/push a `main`.
3. Render tiene `autoDeploy: true`, por lo que reconstruirá el contenedor automáticamente.
4. Cuando esté Live, abre `/health`; debe mostrar `ffmpeg: true`, `ffprobe: true`, `js_runtime: node` y `pot_server: true`.
