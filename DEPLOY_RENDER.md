# LushiTube — despliegue gratuito en Render

Esta carpeta ya está preparada para desplegarse como **Web Service / Docker** en Render.

## Qué incluye

- Flask + Gunicorn
- Node.js 22 (runtime JavaScript que usa yt-dlp)
- FFmpeg + FFprobe
- yt-dlp y sus dependencias
- `render.yaml` para el plan Free
- Binding automático a `0.0.0.0:$PORT`

## Opción recomendada: GitHub + Render

### 1. Sube esta carpeta a GitHub

Crea un repositorio, por ejemplo `LushiTube`, y sube **el contenido de esta carpeta**. El archivo `Dockerfile` debe quedar en la raíz del repositorio, junto a `app.py`.

Si usas Git por terminal:

```bash
git init
git add .
git commit -m "Deploy LushiTube"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/LushiTube.git
git push -u origin main
```

### 2. Crea el servicio en Render

1. Entra a Render.
2. `New` → `Web Service`.
3. Conecta tu cuenta de GitHub y elige el repositorio `LushiTube`.
4. Render debería detectar el `Dockerfile`.
5. Runtime: **Docker**.
6. Plan/Compute: **Free**.
7. Health Check Path: `/`.
8. Crea el servicio.

Si Render ofrece importar `render.yaml`, también puedes usar `New` → `Blueprint` y seleccionar el repositorio.

## Después del deploy

Render te dará una URL parecida a:

`https://lushitube.onrender.com`

La primera carga después de un periodo sin visitas puede tardar porque las instancias gratuitas se suspenden cuando están inactivas.

## Notas para LushiTube

- El almacenamiento local es temporal. Esto es correcto para LushiTube porque los archivos descargados/convertidos se entregan al navegador y luego se eliminan.
- El plan gratuito tiene recursos limitados; videos grandes o conversiones pesadas con FFmpeg pueden tardar bastante.
- Las descargas que salen desde Render hacia el navegador consumen ancho de banda mensual del servicio.
- Si un enlace funciona en tu PC y devuelve 403 únicamente en Render, puede tratarse de una restricción del proveedor de origen hacia IPs de centro de datos, no de Flask.

## Probar localmente con Docker (opcional)

```bash
docker build -t lushitube .
docker run --rm -p 5000:10000 -e PORT=10000 lushitube
```

Abre `http://localhost:5000`.
