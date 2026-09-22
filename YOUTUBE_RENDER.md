# YouTube en Render — LushiTube v4

## Qué cambió

LushiTube distingue ahora entre **leer la ficha del video** y **descargar el stream**. Que título y miniatura aparezcan no significa que la IP del servidor tenga permiso para recuperar el archivo multimedia.

Para YouTube, `/descargar` prueba automáticamente varias rutas, una detrás de otra:

1. `mweb` + PO Token (BgUtils)
2. HLS de `web_safari`
3. `web_embedded`
4. `visionos`
5. `android_vr`
6. sesión autorizada, solo si el propietario configuró cookies explícitamente
7. configuración automática de la versión actual de yt-dlp

La interfaz muestra la ruta activa y avisa cuando cambia automáticamente de estrategia.

## Diagnóstico

Abre:

`https://TU-SERVICIO.onrender.com/health`

Revisa especialmente:

- `ffmpeg: true`
- `ffprobe: true`
- `js_runtime: "node"`
- `pot_plugin: "2.0.0"`
- `pot_server: true`
- `youtube_cloud_mode: "multi-route-v4"`

## Si YouTube sigue rechazando Render

YouTube puede bloquear tráfico anónimo de algunas IP de centros de datos. Un PO Token ayuda con la autenticidad de las solicitudes, pero no garantiza recuperar un stream cuando la IP de salida ya está bloqueada.

LushiTube admite dos opciones **opcionales** mediante variables de entorno de Render:

### `YTDLP_PROXY`

Proxy HTTP/HTTPS propio o de confianza para que yt-dlp use otra salida de red. No se incluye ningún proxy gratuito ni se recomienda publicar credenciales en GitHub.

### `YOUTUBE_COOKIES_B64`

Acepta un `cookies.txt` de YouTube en formato Netscape codificado como Base64. **No se recomienda usar las cookies de tu cuenta personal como solución general**: YouTube puede invalidarlas y el uso automatizado de una cuenta tiene riesgo de bloqueo. Solo se contempla para contenido que legítimamente requiere una sesión y bajo responsabilidad del propietario del despliegue.

## Seguridad

- El servidor BgUtils escucha solo en `127.0.0.1:4416` dentro del contenedor.
- No pongas cookies, proxies ni secretos dentro del repositorio público.
- Usa Render > Environment para cualquier secreto.
