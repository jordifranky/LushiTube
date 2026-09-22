# Corrección específica para HTTP 403 de YouTube

Esta revisión no cambia el diseño. Corrige el flujo de descarga.

- Mantiene la descarga normal como primera opción.
- Ante un 403 de YouTube, reintenta sin obligar al usuario a volver a pulsar el botón.
- Si existe `bgutil-ytdlp-pot-provider`, utiliza `mweb` con PO Token.
- Si no existe, prueba `web_safari` con HLS.
- Como último recurso usa el formato 18 combinado, que sacrifica calidad antes de devolver un error.
- Cada descarga usa un directorio temporal independiente para que los reintentos no reutilicen fragmentos `.part`.
- El endpoint `/status/<uid>` informa también cuando LushiTube está cambiando de ruta por compatibilidad.

La razón del cambio es la aplicación progresiva de PO Tokens por YouTube. Un runtime JS (Node/Deno) resuelve los desafíos JavaScript, pero no sustituye un PO Token de GVS cuando YouTube lo exige.
