from flask import Flask, render_template, request, send_file, jsonify
import yt_dlp
import os
import traceback
import subprocess
import uuid
import threading
import shutil
import re
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
    # No forzamos player_client ni desactivamos JavaScript. Esos "hacks" provocaban
    # formatos 403 en YouTube moderno. yt-dlp decide el cliente apropiado.
    opts = {
        'quiet': True,
        'noplaylist': True,
        'retries': 3,
        'fragment_retries': 3,
        'file_access_retries': 2,
        'socket_timeout': 25,
        'check_formats': 'selected',
    }
    if JS_RUNTIMES:
        opts['js_runtimes'] = JS_RUNTIMES
    return opts


def _is_youtube_url(value):
    try:
        host = (urlparse(value).hostname or '').lower()
        return host == 'youtu.be' or host.endswith('youtube.com') or host.endswith('youtube-nocookie.com')
    except ValueError:
        return False


def _is_http_403(exc):
    text = str(exc).lower()
    return 'http error 403' in text or '403: forbidden' in text or 'forbidden' in text


def _po_provider_config():
    """Detecta la instalación opcional del proveedor de PO Tokens recomendado por yt-dlp."""
    try:
        importlib_metadata.version('bgutil-ytdlp-pot-provider')
    except importlib_metadata.PackageNotFoundError:
        return None
    except Exception:
        return None

    server_home = os.path.join(os.path.expanduser('~'), 'bgutil-ytdlp-pot-provider', 'server')
    candidates = [
        os.path.join(server_home, 'build', 'generate_once.js'),
        os.path.join(server_home, 'src', 'main.ts'),
    ]
    if not any(os.path.isfile(path) for path in candidates):
        return None
    return server_home


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
    """Perfiles de recuperación para los 403 recientes de YouTube.

    1) PO Token si el usuario instaló el proveedor recomendado.
    2) web_safari + HLS, que evita GVS con PO Token en muchos vídeos públicos.
    3) format 18 como último modo de compatibilidad (calidad limitada).
    """
    profiles = []
    po_home = _po_provider_config()
    if po_home:
        profiles.append({
            'name': 'po-token',
            'label': 'Verificando reproducción con YouTube…',
            'detail': 'Usando el proveedor local de PO Token.',
            'extractor_args': {
                'youtube': {'player_client': ['mweb']},
                'youtubepot-bgutilscript': {'server_home': [po_home]},
            },
            'format': 'bestaudio[acodec!=none]/bestaudio/best' if formato in {'mp3', 'wav'} else 'bv*+ba/b',
        })

    hls_format = (
        'bestaudio[protocol*=m3u8]/best[protocol*=m3u8]/18'
        if formato in {'mp3', 'wav'}
        else 'best[protocol*=m3u8][vcodec!=none][acodec!=none]/best[protocol*=m3u8]/18'
    )
    profiles.append({
        'name': 'web-safari-hls',
        'label': 'Cambiando a una ruta de reproducción compatible…',
        'detail': 'YouTube rechazó el flujo directo; probando HLS seguro.',
        'extractor_args': {'youtube': {'player_client': ['web_safari']}},
        'format': hls_format,
    })
    profiles.append({
        'name': 'compat-18',
        'label': 'Aplicando modo de compatibilidad…',
        'detail': 'Último intento con un formato combinado ampliamente compatible.',
        'extractor_args': {'youtube': {'player_client': ['android_vr']}},
        'format': '18',
    })
    return profiles


def _friendly_download_error(exc):
    message = str(exc)
    lowered = message.lower()
    if 'http error 403' in lowered or 'forbidden' in lowered:
        if not JS_RUNTIMES:
            return ('YouTube rechazó la descarga (403). Falta un runtime JavaScript compatible. '
                    'Instala Deno 2.3+ o Node.js 22+ y reinicia LushiTube.')
        return ('YouTube rechazó las rutas de reproducción disponibles (403). '
                'LushiTube ya intentó rutas alternativas. Para máxima compatibilidad ejecuta '
                'INSTALAR_COMPATIBILIDAD_YOUTUBE.bat una sola vez y reinicia la aplicación.')
    if 'sign in' in lowered or 'login' in lowered or 'cookies' in lowered:
        return 'Ese contenido requiere autenticación y no puede descargarse como enlace público.'
    if 'private video' in lowered or 'video unavailable' in lowered:
        return 'El contenido no está disponible públicamente o es privado.'
    return 'No se pudo completar la descarga. Verifica el enlace y vuelve a intentarlo.'

# ===== INFO DEL VIDEO =====
@app.route('/info', methods=['POST'])
def obtener_info():
    payload = request.get_json(silent=True) or {}
    url = (payload.get('url') or '').strip()
    if not is_valid_public_url(url):
        return jsonify({'error': 'Ingresa una URL http o https válida.'}), 400

    try:
        ydl_opts = get_base_ydl_opts()
        ydl_opts['skip_download'] = True

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
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
                'runtime': next(iter(JS_RUNTIMES), None)
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

    progress_data[uid] = {
        'status': 'Resolviendo la fuente…',
        'percent': 3,
        'stage': 'connect',
        'detail': f'Preparando salida {formato.upper()}.',
        'done': False,
    }

    job_dir = os.path.join(DOWNLOAD_FOLDER, f'job_{secure_filename(uid)}')
    _reset_job_dir(job_dir)

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
            }
        elif d['status'] == 'finished':
            progress_data[uid] = {
                'status': 'Transferencia terminada. Preparando el archivo…',
                'percent': 88,
                'stage': 'process',
                'detail': 'La descarga terminó; falta procesar el formato final.',
                'speed': '',
                'done': False,
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
            }
        elif d['status'] == 'finished':
            progress_data[uid] = {
                'status': 'Verificando y finalizando archivo…',
                'percent': 97,
                'stage': 'process',
                'detail': 'Últimos ajustes antes de enviarlo al navegador.',
                'speed': '',
                'done': False,
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
                'writethumbnail': True,
                'postprocessors': [
                    {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '320'},
                    {'key': 'EmbedThumbnail'},
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
            opts['extractor_args'] = profile['extractor_args']
            # HLS y format 18 ya vienen combinados; no hace falta pedir múltiples fragmentos agresivamente.
            if profile['name'] in {'web-safari-hls', 'compat-18'}:
                opts['concurrent_fragment_downloads'] = 2
        return opts

    try:
        attempts = [None]
        if _is_youtube_url(url):
            attempts.extend(_youtube_retry_profiles(formato))

        last_exc = None
        info = None
        used_profile = 'direct'

        for attempt_no, profile in enumerate(attempts):
            if attempt_no > 0:
                _reset_job_dir(job_dir)
                used_profile = profile['name']
                progress_data[uid] = {
                    'status': profile['label'],
                    'percent': 7 + min(attempt_no, 3) * 2,
                    'stage': 'connect',
                    'detail': profile['detail'],
                    'speed': '',
                    'retrying': True,
                    'attempt': attempt_no + 1,
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
                # Los perfiles alternativos son exclusivamente para el 403 de YouTube.
                if not (_is_youtube_url(url) and _is_http_403(exc)):
                    raise
                app.logger.warning(
                    'Intento de descarga YouTube falló con 403 (perfil=%s): %s',
                    used_profile, exc,
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
        user_message = _friendly_download_error(exc)
        progress_data[uid] = {
            'error': user_message,
            'status': user_message,
            'percent': 0,
            'stage': 'error',
            'detail': 'La transferencia se detuvo después de probar las rutas compatibles disponibles.',
            'done': True,
        }
        shutil.rmtree(job_dir, ignore_errors=True)
        return jsonify({'error': user_message}), 422

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
    extensiones_validas = {'wav', 'ogg', 'flac', 'aac', 'm4a', 'wma', 'opus', 'webm', 'mp4', 'avi', 'mkv', 'mov'}
    
    if ext not in extensiones_validas:
        return jsonify({'error': f'Formato .{ext} no soportado. Usa: WAV, OGG, FLAC, AAC, M4A, WMA, OPUS'}), 400
    
    try:
        # Guardar archivo temporal
        temp_id = uuid.uuid4().hex[:12]
        input_path = os.path.join(CONVERT_FOLDER, f'input_{temp_id}.{ext}')
        nombre_base = secure_filename(archivo.filename.rsplit('.', 1)[0]) or 'archivo'
        output_path = os.path.join(CONVERT_FOLDER, f'{nombre_base}_{temp_id}.mp3')
        
        archivo.save(input_path)
        
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
    extensiones_validas = {'avi', 'mkv', 'mov', 'wmv', 'webm', 'flv', 'ts', 'm4v', '3gp', 'ogv', 'mpg', 'mpeg'}
    
    if ext not in extensiones_validas:
        return jsonify({'error': f'Formato .{ext} no soportado. Usa: AVI, MKV, MOV, WMV, WEBM, FLV'}), 400
    
    try:
        # Guardar archivo temporal
        temp_id = uuid.uuid4().hex[:12]
        input_path = os.path.join(CONVERT_FOLDER, f'input_{temp_id}.{ext}')
        nombre_base = secure_filename(archivo.filename.rsplit('.', 1)[0]) or 'archivo'
        output_path = os.path.join(CONVERT_FOLDER, f'{nombre_base}_{temp_id}.mp4')
        
        archivo.save(input_path)
        
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