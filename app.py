from flask import Flask, render_template, request, send_file, jsonify
import yt_dlp
import os
import traceback
import subprocess
import uuid
import threading
import shutil
import re
import socket
import base64
from importlib import metadata as importlib_metadata
from pathlib import Path
from urllib.parse import urlparse
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max upload

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_FOLDER = os.path.join(BASE_DIR, 'descargas')
CONVERT_FOLDER = os.path.join(BASE_DIR, 'conversiones')
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(CONVERT_FOLDER, exist_ok=True)

progress_data = {}
convert_progress = {}

# Configuración opcional para despliegues cloud.
# YTDLP_PROXY puede apuntar a un proxy propio si el proveedor cloud bloquea YouTube.
# YOUTUBE_COOKIES_B64 acepta un cookies.txt de YouTube codificado en base64.
# No se requiere para enlaces públicos y, por seguridad, se mantiene desactivado por defecto.
YTDLP_PROXY = (os.environ.get('YTDLP_PROXY') or '').strip()
YOUTUBE_COOKIES_B64 = (os.environ.get('YOUTUBE_COOKIES_B64') or '').strip()
YOUTUBE_COOKIE_FILE = None


def _prepare_youtube_cookie_file():
    global YOUTUBE_COOKIE_FILE
    if not YOUTUBE_COOKIES_B64:
        return None
    path = '/tmp/lushitube-youtube-cookies.txt'
    try:
        payload = base64.b64decode(YOUTUBE_COOKIES_B64, validate=True)
        text = payload.decode('utf-8-sig').replace('\r\n', '\n')
        first = text.splitlines()[0].strip() if text.splitlines() else ''
        if first not in {'# Netscape HTTP Cookie File', '# HTTP Cookie File'}:
            raise ValueError('Formato cookies.txt inválido')
        Path(path).write_text(text, encoding='utf-8', newline='\n')
        os.chmod(path, 0o600)
        YOUTUBE_COOKIE_FILE = path
        return path
    except Exception:
        app.logger.warning('YOUTUBE_COOKIES_B64 está definido, pero no pudo cargarse. Se ignorará.')
        YOUTUBE_COOKIE_FILE = None
        return None


_prepare_youtube_cookie_file()


def _human_bytes(value):
    try:
        value = float(value or 0)
    except (TypeError, ValueError):
        return ''
    if value <= 0:
        return ''
    units = ['B', 'KB', 'MB', 'GB']
    size = value
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f'{size:.1f} {unit}' if unit != 'B' else f'{int(size)} B'
        size /= 1024
    return ''


def _eta_text(seconds):
    try:
        seconds = max(0, int(float(seconds)))
    except (TypeError, ValueError):
        return ''
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f'{hours:d}:{minutes:02d}:{secs:02d}'
    return f'{minutes:02d}:{secs:02d}'


def _probe_duration(path):
    """Obtiene duración con ffprobe para poder reportar progreso real de FFmpeg."""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', path],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            value = float((result.stdout or '').strip())
            return value if value > 0 else None
    except Exception:
        pass
    return None


def _probe_stream_types(path):
    """Devuelve los tipos de stream detectados por ffprobe (audio/video)."""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type',
             '-of', 'csv=p=0', path],
            capture_output=True, text=True, timeout=20
        )
        if result.returncode == 0:
            return {line.strip().lower() for line in (result.stdout or '').splitlines() if line.strip()}
    except Exception:
        pass
    return set()


def _pot_server_available(host='127.0.0.1', port=4416):
    """Comprueba rápidamente si el proveedor local de PO Token está escuchando."""
    try:
        with socket.create_connection((host, port), timeout=0.35):
            return True
    except OSError:
        return False


def _youtube_pot_extractor_args():
    return {
        'youtube': {'player_client': ['mweb']},
        'youtubepot-bgutilhttp': {'base_url': ['http://127.0.0.1:4416']},
    }


def _run_ffmpeg_with_progress(cmd, duration, uid, label):
    """Ejecuta FFmpeg y publica porcentaje/velocidad en /convert-status/<uid>."""
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )
    current_percent = 14.0
    current_speed = ''
    stderr_text = ''

    if uid:
        convert_progress[uid] = {
            'status': label,
            'percent': current_percent,
            'stage': 'process',
            'detail': 'FFmpeg inició el procesamiento.',
            'done': False,
        }

    if process.stdout:
        for raw_line in process.stdout:
            line = raw_line.strip()
            if '=' not in line:
                continue
            key, value = line.split('=', 1)

            if key == 'speed' and value and value != 'N/A':
                current_speed = value
            elif key in {'out_time_us', 'out_time_ms'} and duration:
                try:
                    # FFmpeg reporta microsegundos tanto en out_time_us como en out_time_ms.
                    elapsed = float(value) / 1_000_000
                    current_percent = min(96.0, 14.0 + (elapsed / duration) * 82.0)
                except (TypeError, ValueError, ZeroDivisionError):
                    pass
            elif key == 'progress':
                if value == 'continue' and not duration:
                    current_percent = min(94.0, current_percent + 3.5)
                elif value == 'end':
                    current_percent = 98.0

            if uid and key in {'out_time_us', 'out_time_ms', 'progress', 'speed'}:
                convert_progress[uid] = {
                    'status': label,
                    'percent': round(current_percent, 1),
                    'stage': 'process',
                    'speed': current_speed,
                    'detail': f'Procesando con FFmpeg{f" · {current_speed}" if current_speed else ""}.',
                    'done': False,
                }

    if process.stderr:
        stderr_text = process.stderr.read() or ''
    return_code = process.wait()
    return return_code, stderr_text


def is_valid_public_url(value):
    """Basic guardrail before handing a URL to yt-dlp."""
    try:
        parsed = urlparse((value or '').strip())
        return parsed.scheme in {'http', 'https'} and bool(parsed.netloc)
    except ValueError:
        return False

@app.route('/health')
def health():
    try:
        pot_plugin = importlib_metadata.version('bgutil-ytdlp-pot-provider')
    except Exception:
        pot_plugin = None
    try:
        ytdlp_version = importlib_metadata.version('yt-dlp')
    except Exception:
        ytdlp_version = None
    try:
        curl_cffi_version = importlib_metadata.version('curl-cffi')
    except Exception:
        curl_cffi_version = None
    try:
        ejs_version = importlib_metadata.version('yt-dlp-ejs')
    except Exception:
        ejs_version = None

    return jsonify({
        'ok': True,
        'ffmpeg': bool(shutil.which('ffmpeg')),
        'ffprobe': bool(shutil.which('ffprobe')),
        'js_runtime': next(iter(JS_RUNTIMES), None) if 'JS_RUNTIMES' in globals() else None,
        'yt_dlp': ytdlp_version,
        'yt_dlp_ejs': ejs_version,
        'curl_cffi': curl_cffi_version,
        'pot_plugin': pot_plugin,
        'pot_server': _pot_server_available() if '_pot_server_available' in globals() else False,
        'proxy_configured': bool(YTDLP_PROXY),
        'youtube_cookies_configured': bool(YOUTUBE_COOKIE_FILE),
        'youtube_cloud_mode': 'multi-route-v5',
        'soundcloud_cloud_mode': 'progressive-hls-v5',
    })


# ===== RUTAS DE PÁGINAS =====
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/terminos')
def terminos():
    return render_template('terminos.html')

@app.route('/privacidad')
def privacidad():
    return render_template('privacidad.html')

# ===== PROGRESO DE DESCARGA =====
@app.route('/status/<uid>')
def download_status(uid):
    return jsonify(progress_data.get(uid, {'status': 'Conectando...', 'percent': 0, 'stage': 'connect', 'done': False}))

# ===== PROGRESO DE CONVERSIÓN =====
@app.route('/convert-status/<uid>')
def convert_status(uid):
    return jsonify(convert_progress.get(uid, {'status': 'Preparando...', 'percent': 0, 'stage': 'prepare', 'done': False}))

# ===== LÓGICA FUNCIONAL: Configuración base de yt-dlp =====
def _version_tuple(text):
    nums = re.findall(r'\d+', text or '')
    return tuple(int(x) for x in nums[:3])


def _runtime_path(name):
    """Detecta un runtime JavaScript compatible para los retos actuales de YouTube."""
    path = shutil.which(name)
    if path:
        return path

    if os.name == 'nt':
        home = os.path.expanduser('~')
        local = os.environ.get('LOCALAPPDATA', '')
        candidates = {
            'deno': [
                os.path.join(home, '.deno', 'bin', 'deno.exe'),
                os.path.join(local, 'Programs', 'deno', 'deno.exe'),
            ],
            'node': [
                os.path.join(os.environ.get('ProgramFiles', r'C:\Program Files'), 'nodejs', 'node.exe'),
                os.path.join(local, 'Programs', 'nodejs', 'node.exe'),
            ],
        }.get(name, [])
        for candidate in candidates:
            if candidate and os.path.isfile(candidate):
                return candidate
    return None


def detect_js_runtimes():
    runtimes = {}

    deno = _runtime_path('deno')
    if deno:
        try:
            out = subprocess.run([deno, '--version'], capture_output=True, text=True, timeout=3).stdout
            first = out.splitlines()[0] if out else ''
            if _version_tuple(first) >= (2, 3, 0):
                runtimes['deno'] = {'path': deno}
        except Exception:
            pass

    node = _runtime_path('node')
    if node:
        try:
            out = subprocess.run([node, '--version'], capture_output=True, text=True, timeout=3).stdout.strip()
            if _version_tuple(out) >= (22, 0, 0):
                runtimes['node'] = {'path': node}
        except Exception:
            pass

    return runtimes


JS_RUNTIMES = detect_js_runtimes()


def get_base_ydl_opts():
    # Ajustes conservadores para entornos cloud. IPv4 ayuda con algunos 403 inmediatos
    # y sleep_interval_requests reduce el riesgo de activar límites por ráfagas.
    opts = {
        'quiet': True,
        'noplaylist': True,
        'retries': 4,
        'fragment_retries': 4,
        'extractor_retries': 2,
        'file_access_retries': 2,
        'socket_timeout': 28,
        'source_address': '0.0.0.0',  # equivalente a --force-ipv4
        'sleep_interval_requests': 0.75,
    }
    if JS_RUNTIMES:
        opts['js_runtimes'] = JS_RUNTIMES
    if YTDLP_PROXY:
        opts['proxy'] = YTDLP_PROXY
    return opts


def get_info_ydl_opts():
    """Opciones ligeras para metadata: no valida URLs de medios ni descarga formatos."""
    opts = get_base_ydl_opts()
    opts.pop('check_formats', None)
    opts.update({
        'skip_download': True,
        'ignore_no_formats_error': True,
        'extract_flat': False,
    })
    return opts


def _is_youtube_url(value):
    try:
        host = (urlparse(value).hostname or '').lower()
        return host == 'youtu.be' or host.endswith('youtube.com') or host.endswith('youtube-nocookie.com')
    except ValueError:
        return False


def _is_soundcloud_url(value):
    try:
        host = (urlparse(value).hostname or '').lower()
        return host == 'soundcloud.com' or host.endswith('.soundcloud.com') or host == 'on.soundcloud.com'
    except ValueError:
        return False


def _is_download_error(exc):
    try:
        return isinstance(exc, yt_dlp.utils.DownloadError)
    except Exception:
        return False


def _is_soundcloud_retryable(exc):
    text = str(exc).lower()
    markers = (
        'http error 401', 'http error 403', 'http error 404',
        'forbidden', 'unable to download', 'client id', 'client_id',
        'fragment', 'requested format is not available', 'no formats',
        'connection reset', 'timed out', 'remote end closed connection',
    )
    return _is_download_error(exc) or any(marker in text for marker in markers)


def _soundcloud_error_code(exc):
    text = str(exc).lower()
    if 'client id' in text or 'client_id' in text:
        return 'soundcloud-client-id'
    if 'http error 403' in text or 'forbidden' in text:
        return 'soundcloud-403'
    if 'http error 404' in text:
        return 'soundcloud-404'
    if 'login' in text or 'registered users' in text or 'authentication' in text:
        return 'soundcloud-auth'
    return 'soundcloud-download'


def _is_http_403(exc):
    text = str(exc).lower()
    return 'http error 403' in text or '403: forbidden' in text or 'forbidden' in text


def _is_youtube_retryable(exc):
    """Errores que pueden variar según el cliente de YouTube o la ruta de playback."""
    text = str(exc).lower()
    # Privado/miembros no mejora cambiando de cliente. Todo DownloadError público sí
    # merece pasar por el resto de rutas, porque los mensajes internos de yt-dlp
    # cambian con frecuencia y antes algunos quedaban fuera de la lista.
    if 'private video' in text or 'members-only' in text or 'members only' in text:
        return False
    markers = (
        'http error 403', '403: forbidden', 'forbidden',
        'sign in to confirm you', "confirm you\'re not a bot", 'not a bot',
        'login required', 'authentication required', 'cookies',
        'video unavailable', 'not available on this app', 'no video formats found',
        'requested format is not available', 'only images are available',
        'player response', 'challenge solving failed', 'unable to download',
        'fragment', 'remote end closed connection', 'timed out',
    )
    return _is_download_error(exc) or any(marker in text for marker in markers)


def _youtube_error_code(exc):
    text = str(exc).lower()
    if 'sign in to confirm' in text or 'not a bot' in text:
        return 'youtube-cloud-block'
    if 'http error 403' in text or '403: forbidden' in text or 'forbidden' in text:
        return 'youtube-403'
    if 'private video' in text or 'members-only' in text:
        return 'youtube-private'
    if 'login required' in text or 'authentication required' in text:
        return 'youtube-auth'
    if 'no video formats found' in text or 'only images are available' in text:
        return 'youtube-no-formats'
    return 'download-error'


def _po_provider_config():
    """True cuando el plugin y el servidor local de PO Token están disponibles."""
    try:
        importlib_metadata.version('bgutil-ytdlp-pot-provider')
    except Exception:
        return False
    return _pot_server_available()


def _reset_job_dir(job_dir):
    try:
        shutil.rmtree(job_dir, ignore_errors=True)
    finally:
        os.makedirs(job_dir, exist_ok=True)


def _find_download_result(job_dir, formato):
    wanted = {
        'mp3': {'.mp3'},
        'wav': {'.wav'},
        'mp4': {'.mp4', '.m4v'},
    }.get(formato, set())
    ignored = {'.part', '.ytdl', '.jpg', '.jpeg', '.png', '.webp', '.json', '.description'}
    files = []
    for root, _, names in os.walk(job_dir):
        for name in names:
            path = os.path.join(root, name)
            suffix = Path(name).suffix.lower()
            if suffix in ignored or name.endswith('.part'):
                continue
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            if wanted and suffix in wanted:
                files.append((2, size, path))
            elif suffix in {'.mp3', '.wav', '.mp4', '.m4a', '.webm', '.mkv', '.opus', '.ogg'}:
                files.append((1, size, path))
    if not files:
        return None
    files.sort(reverse=True)
    return files[0][2]


def _youtube_retry_profiles(formato):
    """
    Rutas de YouTube ordenadas por compatibilidad actual. No todas funcionarán
    desde todas las IP de datacenter; por eso se prueban de manera automática.
    """
    audio = formato in {'mp3', 'wav'}
    profiles = []

    if _po_provider_config():
        profiles.append({
            'name': 'po-token-mweb',
            'public_name': 'PO Token · mweb',
            'label': 'Validando la sesión de reproducción…',
            'detail': 'Generando un PO Token temporal para YouTube.',
            'extractor_args': _youtube_pot_extractor_args(),
            'format': 'bestaudio[acodec!=none]/best[acodec!=none]/18' if audio else 'bv*+ba/b',
            'opts': {'impersonate': 'chrome'},
        })

    # web_safari expone HLS que actualmente puede funcionar sin PO Token GVS.
    profiles.append({
        'name': 'web-safari-hls',
        'public_name': 'HLS · Safari',
        'label': 'Probando reproducción HLS…',
        'detail': 'La ruta principal fue rechazada; probando un flujo HLS compatible.',
        'extractor_args': {'youtube': {'player_client': ['web_safari']}},
        'format': 'bestaudio[protocol*=m3u8]/best[protocol*=m3u8]/18' if audio else 'best[protocol*=m3u8]/18',
        'opts': {'impersonate': 'safari'},
    })

    # web_embedded no exige PO Token, aunque solo funciona en videos embebibles.
    profiles.append({
        'name': 'web-embedded',
        'public_name': 'Embedded',
        'label': 'Probando reproductor embebido…',
        'detail': 'Intentando una sesión sin PO Token para contenido embebible.',
        'extractor_args': {'youtube': {'player_client': ['web_embedded']}},
        'format': 'bestaudio/best' if audio else 'bv*+ba/b',
        'opts': {'impersonate': 'chrome'},
    })

    # visionos forma parte de los clientes por defecto actuales de yt-dlp.
    profiles.append({
        'name': 'visionos',
        'public_name': 'VisionOS',
        'label': 'Cambiando de cliente de reproducción…',
        'detail': 'Probando un cliente alternativo mantenido por yt-dlp.',
        'extractor_args': {'youtube': {'player_client': ['visionos']}},
        'format': 'bestaudio/best' if audio else 'bv*+ba/b',
        'opts': {},
    })

    # Última ruta sin PO Token para algunos videos públicos.
    profiles.append({
        'name': 'android-vr',
        'public_name': 'Android VR',
        'label': 'Aplicando modo de compatibilidad…',
        'detail': 'Último cliente público antes de abandonar la transferencia.',
        'extractor_args': {'youtube': {'player_client': ['android_vr']}},
        'format': 'bestaudio/best/18' if audio else '18/best',
        'opts': {},
    })

    # Autenticación opcional. Solo se usa si el propietario del despliegue añadió
    # YOUTUBE_COOKIES_B64 de forma explícita en Render.
    if YOUTUBE_COOKIE_FILE:
        profiles.append({
            'name': 'cookies',
            'public_name': 'Sesión autorizada',
            'label': 'Probando sesión autorizada…',
            'detail': 'Usando la sesión privada configurada por el propietario del servidor.',
            'extractor_args': {},
            'format': 'bestaudio/best' if audio else 'bv*+ba/b',
            'opts': {'cookiefile': YOUTUBE_COOKIE_FILE},
        })

    return profiles


def _soundcloud_retry_profiles(formato):
    """
    SoundCloud expone varias familias de streams. En cloud evitamos priorizar el
    endpoint de descarga original (que puede requerir cuenta) y probamos primero
    audio progresivo y después HLS.
    """
    if formato not in {'mp3', 'wav'}:
        return []
    common_headers = {
        'Referer': 'https://soundcloud.com/',
        'Origin': 'https://soundcloud.com',
    }
    return [
        {
            'name': 'soundcloud-progressive',
            'public_name': 'SoundCloud · HTTP',
            'label': 'Conectando con el stream de SoundCloud…',
            'detail': 'Probando audio progresivo sin usar la descarga original de cuenta.',
            'format': 'bestaudio[protocol^=http][format_id!*=download]/bestaudio[protocol^=http]/bestaudio/best',
            'opts': {
                'impersonate': 'chrome',
                'cachedir': False,
                'http_headers': common_headers,
            },
        },
        {
            'name': 'soundcloud-hls',
            'public_name': 'SoundCloud · HLS',
            'label': 'Cambiando al stream HLS…',
            'detail': 'La ruta progresiva no respondió; probando el flujo AAC/HLS.',
            'format': 'bestaudio[protocol*=m3u8]/bestaudio/best',
            'opts': {
                'impersonate': 'chrome',
                'cachedir': False,
                'http_headers': common_headers,
                'concurrent_fragment_downloads': 2,
            },
        },
    ]


def _friendly_soundcloud_error(exc):
    code = _soundcloud_error_code(exc)
    if code == 'soundcloud-client-id':
        return 'SoundCloud no entregó una sesión pública válida al servidor. LushiTube renovó el cliente y probó rutas alternativas.'
    if code == 'soundcloud-403':
        return 'SoundCloud rechazó la transferencia desde este servidor cloud (403). El enlace sí fue reconocido.'
    if code == 'soundcloud-404':
        return 'SoundCloud dejó de publicar temporalmente la ruta de audio solicitada o el stream cambió.'
    if code == 'soundcloud-auth':
        return 'Ese recurso de SoundCloud requiere una sesión o una descarga habilitada por el autor.'
    return 'SoundCloud reconoció la pista, pero no pudo completar la transferencia desde este servidor.'


def _friendly_download_error(exc):
    message = str(exc)
    lowered = message.lower()
    code = _youtube_error_code(exc)

    if code == 'youtube-cloud-block':
        return (
            'YouTube bloqueó la sesión anónima del servidor cloud. El enlace puede ser público; '
            'el bloqueo suele depender de la IP de Render. LushiTube probó varias rutas de reproducción.'
        )
    if code == 'youtube-403':
        return (
            'YouTube rechazó las rutas de reproducción del servidor (403). '
            'LushiTube ya probó PO Token, HLS y clientes alternativos.'
        )
    if code in {'youtube-auth', 'youtube-private'}:
        return 'Ese contenido requiere una sesión autorizada o no está disponible públicamente.'
    if code == 'youtube-no-formats':
        return 'YouTube no entregó formatos reproducibles a este servidor. Prueba de nuevo o usa otro contenido público.'
    return 'No se pudo completar la descarga. Verifica el enlace y vuelve a intentarlo.'

# ===== INFO DEL VIDEO =====
@app.route('/info', methods=['POST'])
def obtener_info():
    payload = request.get_json(silent=True) or {}
    url = (payload.get('url') or '').strip()
    if not is_valid_public_url(url):
        return jsonify({'error': 'Ingresa una URL http o https válida.'}), 400

    try:
        # Para metadata no comprobamos formatos descargables. En IPs cloud esa
        # validación puede provocar un 403 aun cuando título/miniatura sí son legibles.
        attempts = [('default', None)]
        if _is_soundcloud_url(url):
            # Fuerza a yt-dlp a renovar client_id si SoundCloud cambió sus assets.
            attempts = [('soundcloud-fresh', None), ('default', None)]
        if _is_youtube_url(url):
            if _po_provider_config():
                attempts.append(('po-token-mweb', _youtube_pot_extractor_args()))
            attempts.extend([
                ('web-embedded', {'youtube': {'player_client': ['web_embedded']}}),
                ('web-safari', {'youtube': {'player_client': ['web_safari']}}),
                ('visionos', {'youtube': {'player_client': ['visionos']}}),
                ('android-vr', {'youtube': {'player_client': ['android_vr']}}),
            ])

        info = None
        last_exc = None
        used_profile = 'default'
        for profile_name, extractor_args in attempts:
            try:
                ydl_opts = get_info_ydl_opts()
                if _is_soundcloud_url(url) and profile_name == 'soundcloud-fresh':
                    ydl_opts['cachedir'] = False
                    ydl_opts['impersonate'] = 'chrome'
                    ydl_opts['http_headers'] = {'Referer': 'https://soundcloud.com/', 'Origin': 'https://soundcloud.com'}
                if extractor_args:
                    ydl_opts['extractor_args'] = extractor_args
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                if info:
                    used_profile = profile_name
                    last_exc = None
                    break
            except Exception as exc:
                last_exc = exc
                app.logger.warning('Metadata falló (perfil=%s): %s', profile_name, exc)
                continue
        if last_exc is not None or info is None:
            raise last_exc or RuntimeError('No se pudo obtener metadata')

        duracion_segundos = info.get('duration') or 0
        minutos, segundos = divmod(int(duracion_segundos), 60)
        thumbnail_url = info.get('thumbnail') or (
            info.get('thumbnails', [{}])[-1].get('url', '') if info.get('thumbnails') else ''
        )
        return jsonify({
            'title': info.get('title', 'Contenido multimedia'),
            'thumbnail': thumbnail_url,
            'duration': f"{minutos:02d}:{segundos:02d}",
            'platform': info.get('extractor_key', '').lower(),
            'runtime_ready': bool(JS_RUNTIMES),
            'runtime': next(iter(JS_RUNTIMES), None),
            'pot_ready': _po_provider_config(),
            'info_profile': used_profile,
        })
    except Exception as exc:
        app.logger.warning('No se pudo obtener metadata: %s', exc)
        return jsonify({'error': 'No se pudo leer ese enlace. Puede ser privado, no compatible o requerir autenticación.'}), 422

@app.route('/descargar', methods=['POST'])
def descargar():
    url = (request.form.get('url') or '').strip()
    formato = (request.form.get('formato') or '').lower()
    uid = request.form.get('uid') or uuid.uuid4().hex[:14]

    if not is_valid_public_url(url):
        progress_data[uid] = {'error': 'URL inválida', 'done': True}
        return jsonify({'error': 'URL inválida'}), 400
    if formato not in {'mp3', 'wav', 'mp4'}:
        progress_data[uid] = {'error': 'Formato no soportado', 'done': True}
        return jsonify({'error': 'Formato no soportado'}), 400

    if _is_soundcloud_url(url) and formato == 'mp4':
        message = 'SoundCloud es una fuente de audio. Elige MP3 o WAV para esta pista.'
        progress_data[uid] = {'error': message, 'error_code': 'soundcloud-audio-only', 'done': True}
        return jsonify({'error': message, 'error_code': 'soundcloud-audio-only'}), 400

    progress_data[uid] = {
        'status': 'Resolviendo la fuente…',
        'percent': 3,
        'stage': 'connect',
        'detail': f'Preparando salida {formato.upper()}.',
        'done': False,
    }

    job_dir = os.path.join(DOWNLOAD_FOLDER, f'job_{secure_filename(uid)}')
    _reset_job_dir(job_dir)

    # Contexto compartido entre los reintentos de YouTube y los hooks de yt-dlp.
    # Así /status conserva qué ruta está activa incluso cuando ya empezó a transferir bytes.
    attempt_context = {
        'attempt': 1,
        'attempt_total': 1,
        'route': 'Auto',
        'retrying': False,
    }

    def _attempt_meta():
        return {
            'attempt': attempt_context.get('attempt', 1),
            'attempt_total': attempt_context.get('attempt_total', 1),
            'route': attempt_context.get('route', 'Auto'),
            'retrying': bool(attempt_context.get('retrying')),
        }

    def my_hook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            downloaded = d.get('downloaded_bytes', 0) or 0
            if total > 0:
                source_percent = (downloaded / total) * 100
                percent = 8 + (source_percent * 0.78)
            else:
                source_percent = 0
                percent = 42

            speed = d.get('speed', 0) or 0
            speed_mb = speed / (1024 * 1024)
            progress_data[uid] = {
                'status': f'Descargando {formato.upper()}…' if source_percent <= 0 else f'Transfiriendo contenido · {source_percent:.0f}%',
                'percent': percent,
                'stage': 'download',
                'speed': f'{speed_mb:.1f} MB/s' if speed_mb > 0 else '',
                'downloaded': _human_bytes(downloaded),
                'total': _human_bytes(total),
                'eta': _eta_text(d.get('eta')) if d.get('eta') is not None else '',
                'done': False,
                **_attempt_meta(),
            }
        elif d['status'] == 'finished':
            progress_data[uid] = {
                'status': 'Transferencia terminada. Preparando el archivo…',
                'percent': 88,
                'stage': 'process',
                'detail': 'La descarga terminó; falta procesar el formato final.',
                'speed': '',
                'done': False,
                **_attempt_meta(),
            }

    def my_pp_hook(d):
        if d['status'] == 'started':
            label = 'Convirtiendo audio con FFmpeg…' if formato in {'mp3', 'wav'} else 'Uniendo pistas y preparando MP4…'
            progress_data[uid] = {
                'status': label,
                'percent': 93,
                'stage': 'process',
                'detail': 'Procesamiento local del archivo final.',
                'speed': '',
                'done': False,
                **_attempt_meta(),
            }
        elif d['status'] == 'finished':
            progress_data[uid] = {
                'status': 'Verificando y finalizando archivo…',
                'percent': 97,
                'stage': 'process',
                'detail': 'Últimos ajustes antes de enviarlo al navegador.',
                'speed': '',
                'done': False,
                **_attempt_meta(),
            }

    def build_options(profile=None):
        opts = get_base_ydl_opts()
        opts.update({
            'outtmpl': os.path.join(job_dir, '%(title).60s_[%(id)s].%(ext)s'),
            'windowsfilenames': True,
            'progress_hooks': [my_hook],
            'postprocessor_hooks': [my_pp_hook],
        })

        if formato == 'mp3':
            opts.update({
                'format': 'bestaudio[acodec!=none]/bestaudio/best',
                'postprocessors': [
                    {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '320'},
                ],
            })
        elif formato == 'wav':
            opts.update({
                'format': 'bestaudio[acodec!=none]/bestaudio/best',
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'wav'}],
            })
        else:
            opts.update({
                'format': 'bv*+ba/b',
                'merge_output_format': 'mp4',
                'postprocessors': [{'key': 'FFmpegVideoRemuxer', 'preferedformat': 'mp4'}],
            })

        if profile:
            opts['format'] = profile['format']
            if profile.get('extractor_args'):
                opts['extractor_args'] = profile['extractor_args']
            opts.update(profile.get('opts') or {})
            if profile['name'] in {'web-safari-hls', 'android-vr'}:
                opts['concurrent_fragment_downloads'] = 2
        return opts

    try:
        attempts = [None]
        is_youtube = _is_youtube_url(url)
        is_soundcloud = _is_soundcloud_url(url)
        platform_name = 'YouTube' if is_youtube else ('SoundCloud' if is_soundcloud else 'Fuente')
        if is_youtube:
            # En cloud empezamos por mweb+PO Token cuando está disponible y después
            # recorremos rutas alternativas. El perfil directo queda como último intento.
            profiles = _youtube_retry_profiles(formato)
            attempts = profiles + [None] if profiles else [None]
        elif is_soundcloud:
            # SoundCloud necesita su propia estrategia; el endpoint original puede
            # requerir login aunque el stream público sí sea reproducible.
            profiles = _soundcloud_retry_profiles(formato)
            attempts = profiles + [None] if profiles else [None]

        last_exc = None
        info = None
        used_profile = 'direct'
        total_attempts = len(attempts)

        for attempt_no, profile in enumerate(attempts):
            if attempt_no > 0:
                _reset_job_dir(job_dir)

            public_name = (profile.get('public_name') or profile['name']) if profile else 'Auto'
            attempt_context.update({
                'attempt': attempt_no + 1,
                'attempt_total': total_attempts,
                'route': public_name,
                'retrying': attempt_no > 0,
            })

            if profile:
                used_profile = profile['name']
                progress_data[uid] = {
                    'status': profile['label'],
                    'percent': min(16, 5 + attempt_no * 2),
                    'stage': 'connect',
                    'detail': profile['detail'],
                    'speed': '',
                    'retrying': attempt_no > 0,
                    'attempt': attempt_no + 1,
                    'attempt_total': total_attempts,
                    'route': public_name,
                    'done': False,
                }
            elif is_youtube or is_soundcloud:
                used_profile = 'direct'
                progress_data[uid] = {
                    'status': 'Probando configuración automática de yt-dlp…',
                    'percent': min(18, 7 + attempt_no * 2),
                    'stage': 'connect',
                    'detail': f'Último intento automático para {platform_name}.',
                    'speed': '',
                    'retrying': attempt_no > 0,
                    'attempt': attempt_no + 1,
                    'attempt_total': total_attempts,
                    'route': 'Auto',
                    'done': False,
                }

            try:
                ydl_opts = build_options(profile)
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
                retryable = (
                    (is_youtube and _is_youtube_retryable(exc))
                    or (is_soundcloud and _is_soundcloud_retryable(exc))
                )
                if not retryable:
                    raise
                app.logger.warning(
                    'Intento de descarga %s recuperable (perfil=%s, intento=%s/%s): %s',
                    platform_name, used_profile, attempt_no + 1, total_attempts, exc,
                )
                continue

        if last_exc is not None:
            raise last_exc

        filename = _find_download_result(job_dir, formato)
        if not filename or not os.path.isfile(filename):
            raise FileNotFoundError('yt-dlp terminó, pero no se encontró el archivo final procesado.')

        progress_data[uid] = {
            'status': 'Archivo listo.',
            'percent': 100,
            'stage': 'process',
            'detail': 'Transferencia completada.',
            'speed': '',
            'profile': used_profile,
            'done': True,
        }

        response = send_file(filename, as_attachment=True, download_name=os.path.basename(filename))

        def cleanup_download():
            import time
            time.sleep(90)
            try:
                shutil.rmtree(job_dir, ignore_errors=True)
            except OSError:
                app.logger.warning('No se pudo limpiar el directorio temporal: %s', job_dir)

        threading.Thread(target=cleanup_download, daemon=True).start()
        return response

    except Exception as exc:
        app.logger.exception('Error durante la descarga')
        if _is_youtube_url(url):
            user_message = _friendly_download_error(exc)
            error_code = _youtube_error_code(exc)
            detail = (
                'El video puede ser público: YouTube está rechazando la IP/sesión del servidor cloud.'
                if error_code in {'youtube-cloud-block', 'youtube-403'}
                else 'La transferencia de YouTube se detuvo después de probar todas las rutas disponibles.'
            )
        elif _is_soundcloud_url(url):
            user_message = _friendly_soundcloud_error(exc)
            error_code = _soundcloud_error_code(exc)
            detail = 'La pista fue reconocida; LushiTube probó stream progresivo, HLS y la ruta automática.'
        else:
            user_message = 'No se pudo completar la descarga. Verifica el enlace y vuelve a intentarlo.'
            error_code = 'download-error'
            detail = 'La transferencia se detuvo antes de completar el archivo.'
        progress_data[uid] = {
            'error': user_message,
            'error_code': error_code,
            'status': user_message,
            'percent': 0,
            'stage': 'error',
            'detail': detail,
            'done': True,
            **_attempt_meta(),
        }
        shutil.rmtree(job_dir, ignore_errors=True)
        return jsonify({
            'error': user_message,
            'error_code': error_code,
            'detail': detail,
            **_attempt_meta(),
        }), 422

@app.route('/convertir-audio', methods=['POST'])
def convertir_audio():
    if 'archivo' not in request.files:
        return jsonify({'error': 'No se recibió ningún archivo'}), 400
    
    archivo = request.files['archivo']
    uid = request.form.get('uid', '')
    
    if archivo.filename == '':
        return jsonify({'error': 'Archivo vacío'}), 400
    
    # Extensiones de audio permitidas
    ext = archivo.filename.rsplit('.', 1)[-1].lower() if '.' in archivo.filename else ''
    extensiones_validas = {'mp3', 'wav', 'flac', 'aac', 'm4a', 'ogg', 'oga', 'opus', 'wma', 'aiff', 'aif', 'ac3', 'amr', 'mp2', 'mka'}
    
    if ext not in extensiones_validas:
        return jsonify({'error': f"Formato .{ext or 'desconocido'} no soportado. Usa MP3, WAV, FLAC, AAC, M4A, OGG, OPUS, WMA, AIFF, AC3, AMR o MKA."}), 400
    
    try:
        # Guardar archivo temporal
        temp_id = uuid.uuid4().hex[:12]
        input_path = os.path.join(CONVERT_FOLDER, f'input_{temp_id}.{ext}')
        nombre_base = secure_filename(archivo.filename.rsplit('.', 1)[0]) or 'archivo'
        output_path = os.path.join(CONVERT_FOLDER, f'{nombre_base}_{temp_id}.mp3')
        
        archivo.save(input_path)

        streams = _probe_stream_types(input_path)
        if 'audio' not in streams:
            try:
                os.remove(input_path)
            except OSError:
                pass
            return jsonify({'error': 'El archivo seleccionado no contiene una pista de audio válida.'}), 400

        duration = _probe_duration(input_path)
        if uid:
            convert_progress[uid] = {
                'status': 'Archivo recibido. Preparando FFmpeg…',
                'percent': 12,
                'stage': 'prepare',
                'detail': 'Validando audio y calculando duración.',
                'done': False,
            }

        # Convertir con FFmpeg y publicar progreso real.
        cmd = [
            'ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', input_path,
            '-vn',
            '-ar', '44100',
            '-ac', '2',
            '-b:a', '320k',
            '-progress', 'pipe:1', '-nostats',
            '-y',
            output_path
        ]
        return_code, ffmpeg_error = _run_ffmpeg_with_progress(cmd, duration, uid, 'Convirtiendo audio a MP3…')
        
        # Limpiar archivo de entrada
        if os.path.exists(input_path):
            os.remove(input_path)
        
        if return_code != 0:
            if uid:
                convert_progress[uid] = {'error': 'Error en la conversión'}
            return jsonify({'error': 'Error al convertir el archivo. Verifica que sea un archivo de audio válido.'}), 500
        
        if uid:
            convert_progress[uid] = {'status': 'MP3 listo.', 'percent': 100, 'stage': 'done', 'detail': 'Conversión completada.', 'done': True}
        
        response = send_file(output_path, as_attachment=True, download_name=f'{nombre_base}.mp3')
        
        # Limpiar archivo de salida después de enviar (en un hilo separado)
        def cleanup():
            import time
            time.sleep(5)
            if os.path.exists(output_path):
                os.remove(output_path)
        threading.Thread(target=cleanup, daemon=True).start()
        
        return response
        
    except subprocess.TimeoutExpired:
        if uid:
            convert_progress[uid] = {'error': 'Tiempo de espera agotado'}
        return jsonify({'error': 'La conversión tardó demasiado. Intenta con un archivo más pequeño.'}), 500
    except Exception as e:
        print("🚨 ERROR CONVERSIÓN AUDIO:")
        traceback.print_exc()
        if uid:
            convert_progress[uid] = {'error': str(e)}
        return jsonify({'error': str(e)}), 500

# ===== CONVERSIÓN DE VIDEO A MP4 =====
@app.route('/convertir-video', methods=['POST'])
def convertir_video():
    if 'archivo' not in request.files:
        return jsonify({'error': 'No se recibió ningún archivo'}), 400
    
    archivo = request.files['archivo']
    uid = request.form.get('uid', '')
    
    if archivo.filename == '':
        return jsonify({'error': 'Archivo vacío'}), 400
    
    # Extensiones de video permitidas
    ext = archivo.filename.rsplit('.', 1)[-1].lower() if '.' in archivo.filename else ''
    extensiones_validas = {'mp4', 'avi', 'mkv', 'mov', 'wmv', 'webm', 'flv', 'ts', 'mts', 'm2ts', 'm4v', '3gp', 'ogv', 'mpg', 'mpeg'}
    
    if ext not in extensiones_validas:
        return jsonify({'error': f"Formato .{ext or 'desconocido'} no soportado. Usa MP4, AVI, MKV, MOV, WMV, WEBM, FLV, MTS, M2TS, MPEG o 3GP."}), 400
    
    try:
        # Guardar archivo temporal
        temp_id = uuid.uuid4().hex[:12]
        input_path = os.path.join(CONVERT_FOLDER, f'input_{temp_id}.{ext}')
        nombre_base = secure_filename(archivo.filename.rsplit('.', 1)[0]) or 'archivo'
        output_path = os.path.join(CONVERT_FOLDER, f'{nombre_base}_{temp_id}.mp4')
        
        archivo.save(input_path)

        streams = _probe_stream_types(input_path)
        if 'video' not in streams:
            try:
                os.remove(input_path)
            except OSError:
                pass
            return jsonify({'error': 'El archivo seleccionado no contiene una pista de video válida.'}), 400

        duration = _probe_duration(input_path)
        if uid:
            convert_progress[uid] = {
                'status': 'Archivo recibido. Preparando FFmpeg…',
                'percent': 12,
                'stage': 'prepare',
                'detail': 'Validando video y calculando duración.',
                'done': False,
            }

        # Convertir con FFmpeg (H.264 + AAC) y publicar progreso real.
        cmd = [
            'ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', input_path,
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '23',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-movflags', '+faststart',
            '-progress', 'pipe:1', '-nostats',
            '-y',
            output_path
        ]
        return_code, ffmpeg_error = _run_ffmpeg_with_progress(cmd, duration, uid, 'Codificando video a MP4…')
        
        # Limpiar archivo de entrada
        if os.path.exists(input_path):
            os.remove(input_path)
        
        if return_code != 0:
            if uid:
                convert_progress[uid] = {'error': 'Error en la conversión'}
            return jsonify({'error': 'Error al convertir el archivo. Verifica que sea un archivo de video válido.'}), 500
        
        if uid:
            convert_progress[uid] = {'status': 'MP4 listo.', 'percent': 100, 'stage': 'done', 'detail': 'Conversión completada.', 'done': True}
        
        response = send_file(output_path, as_attachment=True, download_name=f'{nombre_base}.mp4')
        
        # Limpiar archivo de salida después de enviar
        def cleanup():
            import time
            time.sleep(5)
            if os.path.exists(output_path):
                os.remove(output_path)
        threading.Thread(target=cleanup, daemon=True).start()
        
        return response
        
    except subprocess.TimeoutExpired:
        if uid:
            convert_progress[uid] = {'error': 'Tiempo de espera agotado'}
        return jsonify({'error': 'La conversión tardó demasiado. Intenta con un archivo más pequeño.'}), 500
    except Exception as e:
        print("🚨 ERROR CONVERSIÓN VIDEO:")
        traceback.print_exc()
        if uid:
            convert_progress[uid] = {'error': str(e)}
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    if JS_RUNTIMES:
        print('LushiTube · runtime JS detectado:', ', '.join(JS_RUNTIMES.keys()))
    else:
        print('LushiTube · AVISO: no se detectó Deno 2.3+ ni Node.js 22+. YouTube puede devolver 403.')
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '5000')), debug=os.environ.get('FLASK_DEBUG') == '1')