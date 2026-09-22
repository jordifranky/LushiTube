/* =========================================================
   LushiTube Studio — Interaction layer
   Keeps Flask routes intact: /info, /descargar, /status/<uid>,
   /convertir-audio and /convertir-video.
   ========================================================= */

let currentPlatform = 'youtube';
let currentTab = 'download';
let selectedFormat = 'mp3';
let lastAnalyzedUrl = '';
let activeDownload = null;
let lastDownloadedFilename = '';
let activeConversion = null;

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function uid() {
  return Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-5);
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function fileNameFromDisposition(header, fallback) {
  if (!header) return fallback;
  const utf = header.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf?.[1]) return decodeURIComponent(utf[1]);
  const plain = header.match(/filename="?([^";]+)"?/i);
  return plain?.[1] || fallback;
}

function downloadBlob(blob, filename) {
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.hidden = true;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 25000);
}

function setStatus(message = '', kind = 'error') {
  const status = $('#status-msg');
  if (!status) return;
  status.textContent = message;
  status.dataset.kind = kind;
}

function showLoader(show, text = 'Analizando el enlace…') {
  const loader = $('#loader-area');
  if (!loader) return;
  loader.classList.toggle('visible', show);
  const label = $('#loader-text');
  if (label) label.textContent = text;
}

function setAnalyzeLoading(loading) {
  const button = $('#btn-fetch');
  if (!button) return;
  button.disabled = loading;
  button.classList.toggle('is-loading', loading);
  button.setAttribute('aria-busy', String(loading));
  const input = $('#url-input');
  if (input) input.setAttribute('aria-busy', String(loading));
  const label = $('.action-label', button);
  if (label) label.textContent = loading ? 'Analizando enlace…' : 'Analizar enlace';
}

/* ---------- Init ---------- */
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initNavigation();
  initTabs();
  initPlatformButtons();
  initFormatCards();
  initDropZones();
  initReveal();
  initParticles();
  initMagneticButtons();
  initClipboard();
  initPreviewActions();

  const input = $('#url-input');
  input?.addEventListener('keydown', event => {
    if (event.key === 'Enter') {
      event.preventDefault();
      fetchVideoInfo();
    }
  });
});

/* ---------- Theme ---------- */
function initTheme() {
  const stored = localStorage.getItem('lushitube-theme');
  const preferred = window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  applyTheme(stored || preferred);
  $('#btn-theme')?.addEventListener('click', () => {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    applyTheme(next);
    localStorage.setItem('lushitube-theme', next);
  });
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const label = $('.theme-label');
  if (label) label.textContent = theme === 'dark' ? 'Oscuro' : 'Claro';
  const themeUse = $('.theme-icon use');
  if (themeUse) themeUse.setAttribute('href', theme === 'dark' ? '#i-moon' : '#i-sun');
  const meta = $('meta[name="theme-color"]');
  if (meta) meta.content = theme === 'dark' ? '#071014' : '#eef0eb';
}

/* ---------- Navigation ---------- */
function initNavigation() {
  const toggle = $('#mobile-nav-toggle');
  const nav = $('#main-nav-links');
  if (!toggle || !nav) return;

  toggle.addEventListener('click', event => {
    event.stopPropagation();
    const open = !nav.classList.contains('is-open');
    nav.classList.toggle('is-open', open);
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? 'Cerrar menú' : 'Abrir menú');
  });

  nav.addEventListener('click', event => {
    const link = event.target.closest('a');
    if (!link) return;
    closeMobileNav();
    $$('.nav-links a').forEach(a => a.classList.remove('active'));
    link.classList.add('active');
    if (link.dataset.nav === 'download') switchTab('download');
    if (link.dataset.nav === 'convert') switchTab('convert-audio');
  });

  document.addEventListener('click', event => {
    if (!nav.contains(event.target) && !toggle.contains(event.target)) closeMobileNav();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') closeMobileNav();
  });
  window.addEventListener('resize', () => {
    if (window.innerWidth > 900) closeMobileNav();
  }, { passive: true });
}

function closeMobileNav() {
  const nav = $('#main-nav-links');
  const toggle = $('#mobile-nav-toggle');
  nav?.classList.remove('is-open');
  toggle?.setAttribute('aria-expanded', 'false');
  toggle?.setAttribute('aria-label', 'Abrir menú');
}

/* ---------- Tabs ---------- */
function initTabs() {
  $$('.main-tab').forEach(button => button.addEventListener('click', () => switchTab(button.dataset.tab)));
}

function switchTab(tabName) {
  currentTab = tabName;
  $$('.main-tab').forEach(button => {
    const active = button.dataset.tab === tabName;
    button.classList.toggle('active', active);
    button.setAttribute('aria-selected', String(active));
  });
  $$('.tab-panel').forEach(panel => panel.classList.remove('active'));
  $(`#panel-${tabName}`)?.classList.add('active');

  const navLinks = $$('.nav-links a');
  navLinks.forEach(a => a.classList.remove('active'));
  if (tabName === 'download') $('.nav-links a[data-nav="download"]')?.classList.add('active');
  else $('.nav-links a[data-nav="convert"]')?.classList.add('active');
}

/* ---------- Platform ---------- */
function initPlatformButtons() {
  $$('.platform-btn').forEach(button => {
    button.addEventListener('click', () => selectPlatform(button, true));
  });
}

function selectPlatform(button, preserveInput = false) {
  if (!button) return;
  $$('.platform-btn').forEach(btn => btn.classList.remove('active'));
  button.classList.add('active');
  currentPlatform = button.dataset.platform || 'youtube';

  const placeholders = {
    youtube: 'Pega un enlace público de YouTube…',
    tiktok: 'Pega un enlace público de TikTok…',
    instagram: 'Pega un enlace público de Instagram…',
    soundcloud: 'Pega un enlace público de SoundCloud…',
    facebook: 'Pega un enlace público de Facebook…'
  };
  const input = $('#url-input');
  if (input) input.placeholder = placeholders[currentPlatform] || 'Pega aquí el enlace…';
  if (!preserveInput) nuevaConversion(false);
}

function autoDetectPlatform(url) {
  const lower = String(url || '').toLowerCase();
  let platform = 'youtube';
  if (lower.includes('tiktok.com')) platform = 'tiktok';
  else if (lower.includes('instagram.com')) platform = 'instagram';
  else if (lower.includes('soundcloud.com')) platform = 'soundcloud';
  else if (lower.includes('facebook.com') || lower.includes('fb.watch')) platform = 'facebook';
  const btn = $(`.platform-btn[data-platform="${platform}"]`);
  if (btn) selectPlatform(btn, true);
}

/* ---------- Input ---------- */
function handleInput(input) {
  $('#btn-clear').style.display = input.value ? 'grid' : 'none';
  if (input.value) autoDetectPlatform(input.value);
  setStatus('');
}

function handlePaste() {
  window.setTimeout(() => {
    const input = $('#url-input');
    if (input?.value) {
      $('#btn-clear').style.display = 'grid';
      autoDetectPlatform(input.value);
    }
  }, 20);
}

function clearInput() {
  const input = $('#url-input');
  if (!input) return;
  input.value = '';
  input.focus();
  $('#btn-clear').style.display = 'none';
  setStatus('');
}

function initClipboard() {
  $('#paste-button')?.addEventListener('click', async () => {
    try {
      const text = await navigator.clipboard.readText();
      const input = $('#url-input');
      if (!input) return;
      input.value = text.trim();
      handleInput(input);
      input.focus();
    } catch {
      setStatus('Tu navegador no permitió leer el portapapeles. Pega el enlace manualmente.');
    }
  });
}

function isHttpUrl(value) {
  try {
    const parsed = new URL(value);
    return ['http:', 'https:'].includes(parsed.protocol);
  } catch {
    return false;
  }
}

/* ---------- Fetch metadata ---------- */
async function fetchVideoInfo() {
  const input = $('#url-input');
  const url = input?.value.trim() || '';
  if (!url || !isHttpUrl(url)) {
    setStatus('Pega un enlace http o https válido.');
    input?.focus();
    $('#url-box')?.animate?.([
      { transform: 'translateX(0)' }, { transform: 'translateX(-5px)' }, { transform: 'translateX(5px)' }, { transform: 'translateX(0)' }
    ], { duration: 240 });
    return;
  }

  setStatus('');
  setAnalyzeLoading(true);
  showLoader(true, 'Comprobando el enlace y preparando la vista previa…');
  $('#preview-card')?.classList.remove('visible');
  $('#checkmark-download')?.classList.remove('visible');
  $('#progress-area')?.classList.remove('visible');
  $('#progress-fill')?.classList.remove('done', 'error');
  if ($('#progress-fill')) $('#progress-fill').style.width = '0%';
  if ($('#progress-area')) $('#progress-area').dataset.state = 'loading';
  $('#download-progress-track')?.setAttribute('aria-valuenow', '0');
  updateDownloadStages('connect');

  try {
    const response = await fetch('/info', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url })
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || 'No se pudo analizar el enlace.');

    lastAnalyzedUrl = url;
    renderPreview(data);
    showLoader(false);
    setAnalyzeLoading(false);
    $('#preview-card')?.classList.add('visible');
    $('#preview-card')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (error) {
    showLoader(false);
    setAnalyzeLoading(false);
    setStatus(error.message || 'No se pudo analizar el enlace.');
  }
}

function renderPreview(data) {
  const title = $('#video-title');
  const duration = $('#video-duration');
  const badge = $('#meta-platform-badge');
  const author = $('#video-author');
  const img = $('#thumb-img');
  const fallback = $('#thumb-fallback');

  if (title) title.textContent = data.title || 'Contenido multimedia';
  if (duration) duration.textContent = data.duration || '--:--';
  if (badge) badge.textContent = (data.platform || currentPlatform || 'contenido').replace('_', ' ');
  if (author) {
    author.textContent = data.warning || (data.runtime_ready === false
      ? 'Disponible · el servidor puede requerir runtime JS para algunos enlaces.'
      : 'Listo para elegir formato.');
    author.classList.toggle('is-warning', Boolean(data.warning));
  }

  if (img) {
    img.onload = () => { if (fallback) fallback.style.display = 'none'; };
    img.onerror = () => { img.removeAttribute('src'); if (fallback) fallback.style.display = 'grid'; };
    if (data.thumbnail) img.src = data.thumbnail;
    else { img.removeAttribute('src'); if (fallback) fallback.style.display = 'grid'; }
  }

  const platformName = String(data.platform || currentPlatform || '').toLowerCase();
  const mp4Card = $('.format-card[data-format="mp4"]');
  const soundcloudAudioOnly = platformName.includes('soundcloud') || isSoundCloudUrl(lastAnalyzedUrl);
  if (mp4Card) {
    mp4Card.disabled = soundcloudAudioOnly;
    mp4Card.classList.toggle('is-disabled', soundcloudAudioOnly);
    mp4Card.setAttribute('aria-disabled', String(soundcloudAudioOnly));
    const note = $('small', mp4Card);
    if (note) note.textContent = soundcloudAudioOnly ? 'No aplica · SoundCloud es audio' : 'Video · mejor calidad';
  }
  if (soundcloudAudioOnly && selectedFormat === 'mp4') selectedFormat = 'mp3';
  selectFormat(selectedFormat);
}

/* ---------- Format selection ---------- */
function initFormatCards() {
  $$('.format-card').forEach(card => card.addEventListener('click', () => selectFormat(card.dataset.format)));
  $('#download-now')?.addEventListener('click', () => startDownload(selectedFormat));
}

function selectFormat(format) {
  const requestedCard = $(`.format-card[data-format="${format}"]`);
  if (requestedCard?.disabled) format = 'mp3';
  selectedFormat = ['mp3', 'wav', 'mp4'].includes(format) ? format : 'mp3';
  $$('.format-card').forEach(card => {
    const isSelected = card.dataset.format === selectedFormat;
    card.classList.toggle('selected', isSelected);
    const use = $('.format-state use', card);
    if (use) use.setAttribute('href', isSelected ? '#i-check' : '#i-download');
  });
  setDownloadButtonBusy(false, selectedFormat);
}

function setDownloadButtonBusy(loading, format = selectedFormat) {
  const button = $('#download-now');
  if (!button) return;
  const label = $('.button-label', button);
  if (label) label.textContent = loading ? `Descargando ${format.toUpperCase()}…` : `Descargar ${format.toUpperCase()}`;
  button.classList.toggle('is-loading', loading);
  button.setAttribute('aria-busy', String(loading));
}

/* ---------- Download ---------- */
function isYouTubeUrl(value = '') {
  try {
    const host = new URL(value).hostname.toLowerCase();
    return host === 'youtu.be' || host.endsWith('youtube.com') || host.endsWith('youtube-nocookie.com');
  } catch {
    return false;
  }
}

function isSoundCloudUrl(value = '') {
  try {
    const host = new URL(value).hostname.toLowerCase();
    return host === 'soundcloud.com' || host.endsWith('.soundcloud.com') || host === 'on.soundcloud.com';
  } catch {
    return false;
  }
}

function setNetworkActivity(active, retrying = false) {
  const youtube = $('[data-platform="youtube"]');
  if (!youtube) return;
  youtube.classList.toggle('network-active', active);
  youtube.classList.toggle('network-retrying', active && retrying);
}

function routeLabel(meta = {}) {
  const route = meta.route || '';
  const attempt = Number(meta.attempt) || 0;
  const total = Number(meta.attempt_total) || 0;
  if (route && attempt && total > 1) return `Ruta ${attempt}/${total} · ${route}`;
  if (route) return route;
  return 'Ruta automática';
}

async function startDownload(format = selectedFormat) {
  const url = lastAnalyzedUrl || $('#url-input')?.value.trim();
  if (!url) {
    setStatus('Primero analiza un enlace.');
    return;
  }
  if (activeDownload) return;

  selectedFormat = format;
  const id = uid();
  const controller = new AbortController();
  activeDownload = { id, controller };
  setNetworkActivity(isYouTubeUrl(url), false);
  showDownloadProgress(3, 'Conectando con la fuente…', '', { stage: 'connect', route: isYouTubeUrl(url) ? 'YouTube' : 'Auto' });
  $('#checkmark-download')?.classList.remove('visible');
  $('#download-now')?.setAttribute('disabled', 'disabled');
  setDownloadButtonBusy(true, format);

  let polling = true;
  const poll = async () => {
    while (polling && activeDownload?.id === id) {
      try {
        const res = await fetch(`/status/${id}`, { cache: 'no-store' });
        const data = await res.json();
        if (data.error) {
          showDownloadError(data.error, data);
          polling = false;
          break;
        }
        const percent = clamp(Number(data.percent) || 0, 0, 99);
        showDownloadProgress(percent, data.status || 'Procesando…', data.speed || '', data);
        if (data.done) break;
      } catch { /* Keep primary request as source of truth. */ }
      await new Promise(resolve => setTimeout(resolve, 450));
    }
  };
  poll();

  try {
    const form = new FormData();
    form.append('url', url);
    form.append('formato', format);
    form.append('uid', id);

    const response = await fetch('/descargar', { method: 'POST', body: form, signal: controller.signal });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      const requestError = new Error(data.error || 'No se pudo completar la descarga.');
      requestError.meta = data;
      throw requestError;
    }

    const blob = await response.blob();
    const filename = fileNameFromDisposition(response.headers.get('Content-Disposition'), `LushiTube.${format}`);
    polling = false;
    showDownloadProgress(100, 'Archivo listo.', '', { stage: 'process', detail: 'Transferencia y procesado completados.' });
    lastDownloadedFilename = filename;
    downloadBlob(blob, filename);
    showDownloadSuccess(filename);
  } catch (error) {
    polling = false;
    if (error.name !== 'AbortError') showDownloadError(error.message || 'No se pudo completar la descarga.', error.meta || {});
  } finally {
    setNetworkActivity(false, false);
    activeDownload = null;
    $('#download-now')?.removeAttribute('disabled');
    setDownloadButtonBusy(false, selectedFormat);
  }
}

function getDownloadStage(percent, text = '') {
  const normalized = String(text).toLowerCase();
  if (normalized.includes('proces') || normalized.includes('convert') || normalized.includes('final') || percent >= 88) return 'process';
  if (normalized.includes('descarg') || percent >= 8) return 'download';
  return 'connect';
}

function updateDownloadStages(stage) {
  const order = ['connect', 'download', 'process'];
  const activeIndex = Math.max(0, order.indexOf(stage));
  $$('.progress-stages [data-stage]').forEach(item => {
    const index = order.indexOf(item.dataset.stage);
    item.classList.toggle('active', index === activeIndex);
    item.classList.toggle('done', index < activeIndex);
  });
}

function showDownloadProgress(percent, text, speed = '', meta = {}) {
  const area = $('#progress-area');
  const value = clamp(Number(percent) || 0, 0, 100);
  const stage = meta.stage || getDownloadStage(value, text);
  const retrying = Boolean(meta.retrying);
  area?.classList.add('visible');
  if (area) {
    area.dataset.state = value >= 100 ? 'success' : value > 5 ? 'progress' : 'loading';
    area.dataset.retrying = retrying ? 'true' : 'false';
    area.dataset.stage = stage;
  }

  setNetworkActivity(isYouTubeUrl(lastAnalyzedUrl || $('#url-input')?.value || ''), retrying);

  const fill = $('#progress-fill');
  if (fill) {
    fill.style.width = `${Math.max(value, value > 0 ? 2 : 0)}%`;
    fill.classList.toggle('done', value >= 100);
    fill.classList.remove('error');
  }
  const track = $('#download-progress-track');
  track?.setAttribute('aria-valuenow', String(Math.round(value)));

  const eyebrow = $('#transfer-eyebrow');
  if (eyebrow) {
    if (retrying && meta.attempt && meta.attempt_total) {
      eyebrow.textContent = `Ruta alternativa ${meta.attempt}/${meta.attempt_total}`;
    } else {
      eyebrow.textContent = stage === 'connect'
        ? 'Preparando transferencia'
        : stage === 'download'
          ? `Descargando ${selectedFormat.toUpperCase()}`
          : `Procesando ${selectedFormat.toUpperCase()}`;
    }
  }
  if ($('#progress-label')) $('#progress-label').textContent = text || 'Procesando…';
  if ($('#progress-pct')) $('#progress-pct').textContent = `${Math.round(value)}%`;
  if ($('#progress-speed')) $('#progress-speed').textContent = speed || (meta.eta ? `ETA ${meta.eta}` : '—');

  const route = $('#transfer-route');
  if (route) {
    route.textContent = routeLabel(meta);
    route.classList.toggle('is-retrying', retrying);
  }

  const switcher = $('#route-switch');
  if (switcher) switcher.setAttribute('aria-hidden', retrying ? 'false' : 'true');

  // La onda responde a la velocidad real cuando yt-dlp la reporta.
  const speedValue = Number.parseFloat(String(speed).replace(',', '.'));
  if (area) {
    const duration = Number.isFinite(speedValue) && speedValue > 0
      ? clamp(1.25 - Math.log10(speedValue + 1) * 0.46, 0.48, 1.18)
      : (retrying ? 0.72 : 1.12);
    area.style.setProperty('--wave-duration', `${duration}s`);
  }

  const details = [];
  if (meta.downloaded && meta.total) details.push(`${meta.downloaded} / ${meta.total}`);
  else if (meta.downloaded) details.push(meta.downloaded);
  if (meta.eta) details.push(`faltan aprox. ${meta.eta}`);
  if (meta.detail) details.push(meta.detail);
  if (!details.length) {
    details.push(retrying
      ? 'YouTube rechazó una ruta; LushiTube está cambiando de cliente automáticamente.'
      : stage === 'connect'
        ? 'Resolviendo la fuente y el formato disponible.'
        : stage === 'process'
          ? 'FFmpeg está preparando el archivo final.'
          : 'Mantén esta pestaña abierta mientras continúa la transferencia.');
  }
  const detail = $('#progress-detail');
  if (detail) detail.textContent = details.join(' · ');

  const diag = $('#error-diagnostic');
  if (diag) { diag.hidden = true; diag.textContent = ''; }
  updateDownloadStages(stage);
}

function showDownloadError(message, meta = {}) {
  const area = $('#progress-area');
  area?.classList.add('visible');
  if (area) {
    area.dataset.state = 'error';
    area.dataset.retrying = 'false';
    area.dataset.errorCode = meta.error_code || 'download-error';
  }
  setNetworkActivity(false, false);

  const fill = $('#progress-fill');
  if (fill) {
    fill.style.width = '100%';
    fill.classList.add('error');
    fill.classList.remove('done');
  }
  $('#download-progress-track')?.setAttribute('aria-valuenow', '0');
  if ($('#transfer-eyebrow')) $('#transfer-eyebrow').textContent = 'No se pudo completar';
  if ($('#progress-label')) $('#progress-label').textContent = message;
  if ($('#progress-pct')) $('#progress-pct').textContent = 'Error';
  if ($('#progress-speed')) $('#progress-speed').textContent = '—';
  if ($('#progress-detail')) $('#progress-detail').textContent = meta.detail || 'Puedes reintentar sin volver a analizar el enlace.';

  const route = $('#transfer-route');
  if (route) {
    route.textContent = routeLabel(meta);
    route.classList.remove('is-retrying');
  }
  const switcher = $('#route-switch');
  if (switcher) switcher.setAttribute('aria-hidden', 'true');

  const diagnostic = $('#error-diagnostic');
  if (diagnostic) {
    const cloudBlock = ['youtube-cloud-block', 'youtube-cloud-ip-blocked', 'youtube-rate-limit', 'youtube-403'].includes(meta.error_code);
    const soundCloudBlock = String(meta.error_code || '').startsWith('soundcloud-');
    diagnostic.hidden = false;
    diagnostic.innerHTML = cloudBlock
      ? '<strong>YouTube respondió al servidor, pero bloqueó la reproducción.</strong><span>El enlace sí fue reconocido; el problema está en la sesión/IP cloud, no en el título ni en la miniatura.</span>'
      : soundCloudBlock
        ? `<strong>SoundCloud reconoció la pista.</strong><span>${escapeHtml(meta.detail || 'Se probaron las rutas pública HTTP, HLS y automática.')}</span>`
        : `<strong>Diagnóstico</strong><span>${escapeHtml(meta.error_code || 'download-error')}</span>`;
  }

  updateDownloadStages(meta.stage && meta.stage !== 'error' ? meta.stage : 'connect');
  // Reinicia la microanimación de error para que también se perciba en reintentos sucesivos.
  if (area) {
    area.classList.remove('error-pulse');
    void area.offsetWidth;
    area.classList.add('error-pulse');
  }
}

function showDownloadSuccess(filename = lastDownloadedFilename) {
  const area = $('#progress-area');
  if (area) area.dataset.state = 'success';
  if ($('#transfer-eyebrow')) $('#transfer-eyebrow').textContent = 'Completado';
  if ($('#progress-label')) $('#progress-label').textContent = 'Archivo preparado y enviado al navegador.';
  if ($('#progress-detail')) $('#progress-detail').textContent = filename || 'La transferencia terminó correctamente.';
  if ($('#progress-speed')) $('#progress-speed').textContent = '100%';
  updateDownloadStages('process');
  $$('.progress-stages [data-stage]').forEach(item => { item.classList.remove('active'); item.classList.add('done'); });

  const route = $('#transfer-route');
  if (route) { route.textContent = 'Completado'; route.classList.remove('is-retrying'); }
  const switcher = $('#route-switch');
  if (switcher) switcher.setAttribute('aria-hidden', 'true');
  const success = $('#checkmark-download');
  success?.classList.remove('celebrate');
  success?.classList.add('visible');
  if (success) { void success.offsetWidth; success.classList.add('celebrate'); }
  const fileLabel = $('#download-success-file');
  if (fileLabel) fileLabel.textContent = filename ? `${filename} se guardó en tu dispositivo.` : 'El archivo se guardó en tu dispositivo.';
  $('#download-again').onclick = () => startDownload(selectedFormat);
  $('#new-download').onclick = () => nuevaConversion(false);
  $('#retry-download').onclick = () => startDownload(selectedFormat);
  $('#change-link-error').onclick = () => nuevaConversion(false);
}

function nuevaConversion(preserveInput = false) {
  if (activeDownload) {
    activeDownload.controller.abort();
    activeDownload = null;
  }
  lastAnalyzedUrl = '';
  $('#preview-card')?.classList.remove('visible');
  $('#progress-area')?.classList.remove('visible');
  $('#checkmark-download')?.classList.remove('visible');
  $('#progress-fill')?.classList.remove('done', 'error');
  if ($('#progress-fill')) $('#progress-fill').style.width = '0%';
  if ($('#progress-area')) $('#progress-area').dataset.state = 'loading';
  $('#download-progress-track')?.setAttribute('aria-valuenow', '0');
  updateDownloadStages('connect');
  if ($('#progress-detail')) $('#progress-detail').textContent = 'Esperando información de la fuente.';
  if ($('#progress-speed')) $('#progress-speed').textContent = '—';
  if ($('#transfer-route')) { $('#transfer-route').textContent = 'Ruta automática'; $('#transfer-route').classList.remove('is-retrying'); }
  $('#route-switch')?.setAttribute('aria-hidden', 'true');
  const diagnostic = $('#error-diagnostic');
  if (diagnostic) { diagnostic.hidden = true; diagnostic.textContent = ''; }
  if ($('#progress-area')) { $('#progress-area').dataset.retrying = 'false'; $('#progress-area').classList.remove('error-pulse'); }
  setNetworkActivity(false, false);
  lastDownloadedFilename = '';
  setStatus('');
  showLoader(false);
  if (!preserveInput) clearInput();
  $('#url-input')?.focus();
}

function initPreviewActions() {
  $('#preview-close')?.addEventListener('click', () => nuevaConversion(true));
  $('#retry-download')?.addEventListener('click', () => startDownload(selectedFormat));
  $('#change-link-error')?.addEventListener('click', () => nuevaConversion(false));
}

/* ---------- File converters ---------- */
function initDropZones() {
  ['audio', 'video'].forEach(type => {
    const zone = $(`#drop-zone-${type}`);
    const input = $(`#file-input-${type}`);
    if (!zone || !input) return;

    const openPicker = () => input.click();
    zone.addEventListener('click', event => { if (event.target !== input) openPicker(); });
    zone.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openPicker(); }
    });
    ['dragenter', 'dragover'].forEach(name => zone.addEventListener(name, event => {
      event.preventDefault(); zone.classList.add('dragover');
    }));
    ['dragleave', 'drop'].forEach(name => zone.addEventListener(name, event => {
      event.preventDefault(); zone.classList.remove('dragover');
    }));
    zone.addEventListener('drop', event => {
      if (!event.dataTransfer?.files?.length) return;
      input.files = event.dataTransfer.files;
      handleFileSelect(type);
    });
    input.addEventListener('change', () => handleFileSelect(type));
  });
}

function handleFileSelect(type) {
  const input = $(`#file-input-${type}`);
  const zone = $(`#drop-zone-${type}`);
  const button = $(`#btn-convert-${type}`);
  const copy = $('.drop-zone-text', zone);
  const file = input?.files?.[0];
  if (!file) return;

  const audioExts = new Set(['mp3','wav','flac','aac','m4a','ogg','oga','opus','wma','aiff','aif','ac3','amr','mp2','mka']);
  const videoExts = new Set(['mp4','avi','mkv','mov','wmv','webm','flv','ts','mts','m2ts','m4v','3gp','ogv','mpg','mpeg']);
  const ext = (file.name.split('.').pop() || '').toLowerCase();
  const valid = type === 'audio'
    ? (file.type.startsWith('audio/') || audioExts.has(ext))
    : (file.type.startsWith('video/') || videoExts.has(ext));
  if (!valid) {
    input.value = '';
    zone?.classList.remove('has-file');
    const copy = $('.drop-zone-text', zone);
    if (copy) copy.innerHTML = type === 'audio'
      ? '<h4>Ese archivo no parece ser audio</h4><p>Usa MP3, WAV, FLAC, M4A, AAC, OGG, OPUS, WMA o AIFF.</p>'
      : '<h4>Ese archivo no parece ser video</h4><p>Usa MP4, AVI, MKV, MOV, WEBM, WMV, FLV o MPEG.</p>';
    if (button) button.disabled = true;
    return;
  }

  zone?.classList.add('has-file');
  const size = file.size >= 1024 * 1024 ? `${(file.size / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(file.size / 1024))} KB`;
  if (copy) copy.innerHTML = `<h4>${escapeHtml(file.name)}</h4><p>${size} · listo para convertir</p>`;
  if (button) button.disabled = false;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, char => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' }[char]));
}

function setConversionButton(type, label, disabled = false) {
  const button = $(`#btn-convert-${type}`);
  if (!button) return;
  const span = $('span', button);
  if (span) span.textContent = label;
  button.disabled = disabled;
  button.classList.toggle('is-loading', label.includes('…'));
}

async function startConversion(type) {
  const input = $(`#file-input-${type}`);
  const button = $(`#btn-convert-${type}`);
  const file = input?.files?.[0];
  if (!file || !button || activeConversion) return;

  const target = type === 'audio' ? 'MP3' : 'MP4';
  const endpoint = type === 'audio' ? '/convertir-audio' : '/convertir-video';
  const conversionId = uid();
  const form = new FormData();
  form.append('archivo', file);
  form.append('uid', conversionId);

  activeConversion = { id: conversionId, type };
  setConversionButton(type, `Convirtiendo a ${target}…`, true);
  button.setAttribute('aria-busy', 'true');
  const progress = $(`#convert-progress-${type}`);
  const fill = $(`#convert-fill-${type}`);
  const pct = $(`#convert-pct-${type}`);
  const label = $(`#convert-label-${type}`);
  const detail = $(`#convert-detail-${type}`);
  const track = $(`#convert-track-${type}`);
  const success = $(`#checkmark-${type}`);
  progress?.classList.add('active');
  if (progress) progress.dataset.state = 'loading';
  success?.classList.remove('visible');
  fill?.classList.remove('done', 'error');
  if (fill) fill.style.width = '4%';
  if (pct) pct.textContent = '4%';
  track?.setAttribute('aria-valuenow', '4');
  if (label) label.textContent = 'Subiendo archivo…';
  if (detail) detail.textContent = 'Preparando el archivo para FFmpeg.';

  let visualPct = 4;
  let serverPct = 0;
  let polling = true;
  const visualTimer = window.setInterval(() => {
    const cap = serverPct >= 50 ? 94 : 42;
    visualPct = Math.min(cap, visualPct + (visualPct < 25 ? 3 : .8));
    if (fill) fill.style.width = `${visualPct}%`;
    if (pct) pct.textContent = `${Math.floor(visualPct)}%`;
    track?.setAttribute('aria-valuenow', String(Math.floor(visualPct)));
  }, 220);

  const poll = async () => {
    while (polling && activeConversion?.id === conversionId) {
      try {
        const response = await fetch(`/convert-status/${conversionId}`, { cache: 'no-store' });
        const data = await response.json();
        if (data.error) throw new Error(data.error);
        serverPct = Number(data.percent) || 0;
        if (progress) progress.dataset.state = serverPct >= 20 ? 'progress' : 'loading';
        if (label && data.status) label.textContent = data.status;
        if (detail) detail.textContent = data.detail || (data.speed ? `Velocidad de proceso: ${data.speed}` : 'Procesando localmente con FFmpeg.');
        if (serverPct > visualPct && serverPct < 100) visualPct = Math.min(96, serverPct);
        if (data.done) break;
      } catch { /* Main conversion request remains the source of truth. */ }
      await new Promise(resolve => setTimeout(resolve, 500));
    }
  };
  poll();

  try {
    const response = await fetch(endpoint, { method: 'POST', body: form });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.error || 'No se pudo convertir el archivo.');
    }
    const blob = await response.blob();
    polling = false;
    clearInterval(visualTimer);
    if (progress) progress.dataset.state = 'success';
    if (fill) { fill.style.width = '100%'; fill.classList.add('done'); }
    if (pct) pct.textContent = '100%';
    track?.setAttribute('aria-valuenow', '100');
    if (label) label.textContent = `Conversión a ${target} completada.`;
    const fallback = `${file.name.replace(/\.[^.]+$/, '')}.${target.toLowerCase()}`;
    const outputName = fileNameFromDisposition(response.headers.get('Content-Disposition'), fallback);
    downloadBlob(blob, outputName);
    success?.classList.add('visible');
    button.removeAttribute('aria-busy');
    setConversionButton(type, `Convertir otro archivo a ${target}`, false);
    if (detail) detail.textContent = 'Archivo final listo y enviado al navegador.';
    button.onclick = () => resetConverter(type);
  } catch (error) {
    polling = false;
    clearInterval(visualTimer);
    if (progress) progress.dataset.state = 'error';
    if (fill) { fill.style.width = '100%'; fill.classList.add('error'); fill.classList.remove('done'); }
    if (pct) pct.textContent = 'Error';
    track?.setAttribute('aria-valuenow', '0');
    if (label) label.textContent = error.message || 'Error durante la conversión.';
    button.removeAttribute('aria-busy');
    setConversionButton(type, 'Reintentar conversión', false);
    if (detail) detail.textContent = 'Revisa el archivo y vuelve a intentarlo.';
  } finally {
    activeConversion = null;
  }
}

function resetConverter(type) {
  const input = $(`#file-input-${type}`);
  const zone = $(`#drop-zone-${type}`);
  const button = $(`#btn-convert-${type}`);
  const progress = $(`#convert-progress-${type}`);
  const fill = $(`#convert-fill-${type}`);
  const success = $(`#checkmark-${type}`);
  if (input) input.value = '';
  zone?.classList.remove('has-file');
  progress?.classList.remove('active');
  if (progress) progress.dataset.state = 'loading';
  success?.classList.remove('visible');
  if (fill) { fill.style.width = '0%'; fill.classList.remove('done', 'error'); }
  $(`#convert-track-${type}`)?.setAttribute('aria-valuenow', '0');
  const copy = $('.drop-zone-text', zone);
  if (copy) copy.innerHTML = type === 'audio'
    ? '<h4>Suelta tu archivo aquí</h4><p>WAV, FLAC, AAC, M4A, OGG, OPUS y más</p>'
    : '<h4>Suelta tu video aquí</h4><p>AVI, MKV, MOV, WMV, WEBM, FLV y más</p>';
  if (button) {
    setConversionButton(type, type === 'audio' ? 'Convertir a MP3' : 'Convertir a MP4', true);
    const detail = $(`#convert-detail-${type}`);
    if (detail) detail.textContent = 'Esperando al procesador.';
    button.onclick = () => startConversion(type);
  }
}

/* ---------- Reveal & microinteractions ---------- */
function initReveal() {
  const items = $$('.reveal');
  if (!('IntersectionObserver' in window)) {
    items.forEach(item => item.classList.add('is-visible'));
    return;
  }
  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('is-visible');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: .12, rootMargin: '0px 0px -25px 0px' });
  items.forEach((item, index) => {
    item.style.transitionDelay = `${Math.min(index % 4, 3) * 55}ms`;
    observer.observe(item);
  });
}

function initMagneticButtons() {
  if (window.matchMedia('(pointer: coarse)').matches || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  $$('.magnetic').forEach(button => {
    button.addEventListener('pointermove', event => {
      const rect = button.getBoundingClientRect();
      const x = (event.clientX - rect.left - rect.width / 2) * .05;
      const y = (event.clientY - rect.top - rect.height / 2) * .08;
      button.style.transform = `translate(${x}px, ${y}px)`;
    });
    button.addEventListener('pointerleave', () => { button.style.transform = ''; });
  });
}

/* ---------- Lightweight particles ---------- */
function initParticles() {
  const canvas = $('#particles-canvas');
  if (!canvas || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const ctx = canvas.getContext('2d', { alpha: true });
  if (!ctx) return;

  let points = [];
  let width = 0;
  let height = 0;
  let raf = 0;
  const pointer = { x: -9999, y: -9999, active: false };

  const palette = () => document.documentElement.dataset.theme === 'light'
    ? { node: 'rgba(79,135,142,', warm: 'rgba(164,128,69,', line: 'rgba(83,126,128,' }
    : { node: 'rgba(115,174,179,', warm: 'rgba(196,160,96,', line: 'rgba(146,184,179,' };

  function makePoint() {
    return {
      x: Math.random() * width,
      y: Math.random() * height,
      baseX: 0,
      baseY: 0,
      vx: (Math.random() - .5) * .11,
      vy: (Math.random() - .5) * .08,
      r: .55 + Math.random() * 1.25,
      alpha: .12 + Math.random() * .30,
      warm: Math.random() > .82,
      phase: Math.random() * Math.PI * 2
    };
  }

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 1.6);
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const count = Math.min(74, Math.max(28, Math.floor(width / 22)));
    points = Array.from({ length: count }, makePoint);
  }

  function draw(timestamp = 0) {
    ctx.clearRect(0, 0, width, height);
    const colors = palette();
    const maxDistance = width < 700 ? 84 : 118;

    for (const p of points) {
      p.x += p.vx;
      p.y += p.vy;
      if (p.x < -8) p.x = width + 8;
      if (p.x > width + 8) p.x = -8;
      if (p.y < -8) p.y = height + 8;
      if (p.y > height + 8) p.y = -8;

      if (pointer.active) {
        const dx = p.x - pointer.x;
        const dy = p.y - pointer.y;
        const d2 = dx * dx + dy * dy;
        if (d2 < 19000 && d2 > 1) {
          const force = (19000 - d2) / 19000;
          p.x += dx * force * .008;
          p.y += dy * force * .008;
        }
      }
    }

    // Draw only a sparse local network so it reads as a signal map, not star wallpaper.
    for (let i = 0; i < points.length; i++) {
      const a = points[i];
      let links = 0;
      for (let j = i + 1; j < points.length && links < 2; j++) {
        const b = points[j];
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const dist = Math.hypot(dx, dy);
        if (dist < maxDistance) {
          const alpha = (1 - dist / maxDistance) * .105;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.strokeStyle = `${colors.line}${alpha})`;
          ctx.lineWidth = .55;
          ctx.stroke();
          links++;
        }
      }
    }

    for (const p of points) {
      const pulse = .82 + Math.sin(timestamp * .0012 + p.phase) * .18;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r * pulse, 0, Math.PI * 2);
      ctx.fillStyle = `${p.warm ? colors.warm : colors.node}${p.alpha})`;
      ctx.fill();
      if (p.warm && p.r > 1.1) {
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r * 4.2, 0, Math.PI * 2);
        ctx.fillStyle = `${colors.warm}.035)`;
        ctx.fill();
      }
    }
    raf = requestAnimationFrame(draw);
  }

  resize();
  cancelAnimationFrame(raf);
  raf = requestAnimationFrame(draw);
  window.addEventListener('resize', resize, { passive: true });
  window.addEventListener('pointermove', event => {
    pointer.x = event.clientX;
    pointer.y = event.clientY;
    pointer.active = true;
  }, { passive: true });
  window.addEventListener('pointerleave', () => { pointer.active = false; }, { passive: true });
  document.addEventListener('visibilitychange', () => {
    cancelAnimationFrame(raf);
    if (!document.hidden) raf = requestAnimationFrame(draw);
  });
}
