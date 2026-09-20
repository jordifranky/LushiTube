# Corrección Render

1. Reemplaza TODO el contenido del repositorio por esta versión (especialmente Dockerfile, start.sh y app.py).
2. No mezcles el Dockerfile anterior con el nuevo.
3. Render debe usar runtime Docker y `render.yaml` en la raíz.
4. Tras el deploy abre `/health`.

Esperado:
- `ok: true`
- `ffmpeg: true`
- `ffprobe: true`
- `js_runtime: "node"`
- `pot_plugin: "2.0.0"`
- `pot_server: true`

La lectura de metadata de `/info` ya no valida formatos descargables; esto evita falsos 403 en IPs cloud al analizar un enlace.
