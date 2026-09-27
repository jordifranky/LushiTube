# YouTube en Render sin túneles — LushiTube v7

Esta versión usa una sesión de YouTube configurada **dentro de Render** cuando YouTube responde `Sign in to confirm you're not a bot`.

## Importante

- No subas `cookies.txt` a GitHub.
- Usa únicamente una sesión que te pertenezca.
- yt-dlp advierte que automatizar descargas con una cuenta puede provocar bloqueos temporales o permanentes. Para pruebas, es más prudente usar una cuenta secundaria.
- Las cookies pueden expirar o rotarse y habrá que reemplazarlas.
- Incluso con sesión + PO Token, una IP de centro de datos puede seguir siendo limitada. Esta versión es el mejor intento **Render-only**, pero no puede garantizar que YouTube acepte siempre la IP compartida del plan Free.

## Método recomendado: Secret File de Render

1. Genera un archivo `youtube-cookies.txt` en formato Netscape, únicamente con cookies de youtube.com.
2. En Render abre tu servicio `lushitube`.
3. Entra a **Environment**.
4. En **Secret Files** pulsa **Add Secret File**.
5. Filename: `youtube-cookies.txt`
6. Pega el contenido del archivo.
7. Guarda y despliega.

Render lo montará en:

`/etc/secrets/youtube-cookies.txt`

LushiTube v7 lo detecta automáticamente.

## Comprobación

Abre:

`https://lushitube.onrender.com/health`

Debe aparecer:

- `youtube_cookies_configured: true`
- `youtube_auth_mode: "secret-file"`
- `youtube_cloud_mode: "render-auth-first-v7"`
- `pot_server: true`

## Alternativa: variable Base64

La compatibilidad anterior sigue disponible con `YOUTUBE_COOKIES_B64`, pero Secret File es más cómodo para un archivo de cookies y evita poner un valor enorme en una variable.
