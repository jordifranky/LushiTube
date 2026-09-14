# LushiTube Studio — instalación

## Requisitos

- Python 3.11 o superior.
- FFmpeg y FFprobe disponibles en `PATH`.
- Para YouTube moderno: Deno 2.3+ o Node.js 22+.

## Instalación

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -U -r requirements.txt
python app.py
```

Luego abre `http://127.0.0.1:5000`.

En Windows puedes ejecutar `VERIFICAR_ENTORNO.bat` para comprobar Python, yt-dlp, FFmpeg y el runtime JavaScript.

## Flujo de descarga

La interfaz conserva las rutas existentes y consulta `/status/<uid>` mientras una descarga está activa. El estado puede mostrar:

- conexión con la fuente;
- porcentaje descargado;
- velocidad;
- tamaño transferido/total cuando yt-dlp lo informa;
- ETA cuando está disponible;
- procesado de FFmpeg y preparación del archivo final.

## Conversión local

Los conversores mantienen `/convertir-audio`, `/convertir-video` y `/convert-status/<uid>`.

La duración se obtiene con FFprobe y FFmpeg se ejecuta con su salida de progreso (`-progress pipe:1`), de modo que la barra de conversión puede reflejar el tiempo realmente procesado en lugar de depender solo de una animación simulada.

## Diseño

La revisión actual usa una identidad de estudio multimedia/signal desk con una paleta petróleo y mineral, azul verdoso desaturado, latón envejecido y verde salvia. Los colores de cada plataforma aparecen principalmente en sus iconos para evitar una interfaz saturada.

Consulta `REFINAMIENTO_MEDIA_DESK.md` para el detalle de diseño y referencias revisadas.


## Si YouTube responde HTTP 403

LushiTube ahora prueba automáticamente varias rutas de reproducción:

1. descarga normal de máxima calidad;
2. proveedor de PO Token, si está instalado;
3. cliente `web_safari` con HLS;
4. formato combinado de compatibilidad como último recurso.

Tu log puede mostrar un primer 403 y luego continuar: eso significa que entró el **autofallback**.

Para tener la mejor compatibilidad actual en Windows:

- Ejecuta `ACTUALIZAR_YTDLP_NIGHTLY.bat` para usar la rama nightly recomendada por yt-dlp.
- Si determinados videos siguen devolviendo 403, ejecuta una sola vez `INSTALAR_COMPATIBILIDAD_YOUTUBE.bat`. El instalador prepara `bgutil-ytdlp-pot-provider` y LushiTube lo detecta automáticamente al reiniciar.

No es necesario iniciar manualmente un servidor para el modo script configurado por esta versión.
