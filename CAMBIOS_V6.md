# LushiTube Cloud v6

## Correcciones

- Eliminado `impersonate: "chrome"/"safari"` de la API Python de yt-dlp. En versiones actuales ese valor debe llegar convertido a `ImpersonateTarget`; pasarlo como texto desde `YoutubeDL({...})` podía provocar `AssertionError` antes de iniciar la descarga.
- SoundCloud ahora solicita `soundcloud:formats=*`, incluyendo variantes `hls-aes` que no forman parte de la lista predeterminada de formatos solicitados por yt-dlp.
- Añadido segundo perfil de SoundCloud para AAC/OPUS/MP3 y HLS-AES.
- Si una pista solo publica streams DRM reales, se muestra un diagnóstico explícito en lugar de presentarlo como un fallo genérico.
- YouTube deja de hacer seis intentos de metadata consecutivos cuando Render ya está respondiendo 429/403.
- Si yt-dlp es bloqueado por la IP de Render, `/info` intenta usar YouTube oEmbed para mostrar título y miniatura. Esto no convierte oEmbed en una ruta de descarga; la descarga sigue necesitando una salida de red aceptada por YouTube.
- Nuevos diagnósticos `youtube-rate-limit` y `youtube-cloud-ip-blocked`.

## Health

- `youtube_cloud_mode`: `oembed-network-aware-v6`
- `soundcloud_cloud_mode`: `all-streams-v6`
