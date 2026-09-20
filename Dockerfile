# LushiTube - Render ready (Flask + yt-dlp + FFmpeg + PO Token provider)
FROM node:22-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=10000

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 \
      python3-pip \
      python3-venv \
      ffmpeg \
      ca-certificates \
      git \
      curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -U --pre "yt-dlp[default,curl-cffi]"

# Provider PO Token 2.0.0: misma versión que el plugin de requirements.txt.
RUN git clone --depth 1 --branch 2.0.0 \
      https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /opt/bgutil \
    && cd /opt/bgutil/server \
    && npm ci \
    && npx tsc \
    && npm cache clean --force

COPY . .

RUN mkdir -p /app/descargas /app/conversiones \
    && chmod +x /app/start.sh

EXPOSE 10000

# Un único CMD. start.sh levanta primero PO Token y luego Gunicorn.
CMD ["/app/start.sh"]
