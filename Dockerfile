# LushiTube - imagen preparada para Render/Koyeb
# Node 22 se usa como runtime JavaScript de yt-dlp para YouTube.
FROM node:22-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=10000

# Python + FFmpeg/FFprobe para Flask, descargas y conversiones.
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 \
      python3-pip \
      python3-venv \
      ffmpeg \
      ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Entorno Python aislado.
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Directorios temporales. En Render Free el disco es efímero, que aquí es adecuado
# porque LushiTube elimina los archivos tras servirlos.
RUN mkdir -p /app/descargas /app/conversiones

EXPOSE 10000

# Un solo worker para limitar RAM en el plan Free y 4 threads para que /status
# siga respondiendo mientras una descarga/conversión está en curso.
CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads 4 --timeout 1800 --keep-alive 5 --access-logfile - --error-logfile -"]
