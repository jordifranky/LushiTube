# Refinamiento Media Desk

Esta revisión se centró en dos problemas observados en la versión anterior: identidad visual demasiado genérica y falta de una lectura clara del estado real de descarga/conversión.

## Referencias revisadas

Se tomaron patrones funcionales —no estilos copiados— de proyectos reales:

- **cobalt** (`imputnet/cobalt`): flujo de descarga de baja fricción y mensajes inline en lugar de diálogos invasivos.
- **imsyy/yt-dlp-gui**: progreso en tiempo real con velocidad y ETA, preview antes de descargar y estados de descarga visibles.
- **enesehs/yt-dlp-gui**: barra de progreso, velocidad, estado y vista previa como parte de una misma tarea.
- **Raynoxis/yt-dlp-Web-Interface**: transparencia del procesamiento y selección de formato antes de descargar.
- **Stacher 7**: interfaz de herramienta/media manager, temas y gestión explícita del motor yt-dlp/FFmpeg.
- **Media Downloader (ezmdl.com)**: interacción principal centrada en pegar, elegir y descargar sin saturar la pantalla.

## Cambios visuales

- Paleta más sobria: carbón/petróleo, azul verdoso desaturado, latón envejecido y verde salvia.
- Se redujeron glows y contrastes bruscos para evitar apariencia “neón IA”.
- El color propio de YouTube, TikTok, Instagram, SoundCloud y Facebook queda concentrado en sus iconos, no en tarjetas enteras.
- Iconografía SVG inline para plataformas, formatos y acciones. No requiere librerías externas.
- La selección de formato se presenta como módulos de media, con estado visual y pictograma específico.
- El modo claro usa una superficie mineral cálida en vez de blanco puro.

## Descarga: estados visibles

El componente de transferencia ahora muestra permanentemente durante la tarea:

1. **Fuente** — conexión/resolución del enlace.
2. **Transferencia** — descarga con porcentaje, velocidad, bytes transferidos y ETA cuando yt-dlp los entrega.
3. **Procesado** — conversión/mezcla de FFmpeg y preparación del archivo final.

Incluye barra de progreso de 9 px, indicador activo, microonda animada, porcentaje grande, velocidad y detalle contextual.

## Conversión local

`app.py` ahora obtiene la duración con `ffprobe` y ejecuta FFmpeg usando `-progress pipe:1`. Esto permite que `/convert-status/<uid>` publique un porcentaje basado en el tiempo realmente procesado en lugar de mostrar solo un progreso simulado.

Las rutas existentes se mantienen sin cambios.
