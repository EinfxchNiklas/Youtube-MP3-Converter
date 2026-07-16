/* ── Helpers ─────────────────────────────────────────────────────────────── */

/**
 * Parse time string "hh:mm:ss.mmm" OR "mm:ss.mmm" OR "ss.mmm" → milliseconds.
 * Returns NaN on invalid input.
 */
function parseTimeToMs(str) {
  if (!str || !str.trim()) return NaN;
  str = str.trim();

  // Allow both : and . as separators, normalise
  const parts = str.split(':');
  let h = 0, m = 0, s = 0;

  if (parts.length === 3) {
    h = parseInt(parts[0], 10);
    m = parseInt(parts[1], 10);
    s = parseFloat(parts[2]);
  } else if (parts.length === 2) {
    m = parseInt(parts[0], 10);
    s = parseFloat(parts[1]);
  } else {
    s = parseFloat(parts[0]);
  }

  if (isNaN(h) || isNaN(m) || isNaN(s)) return NaN;
  return Math.round((h * 3600 + m * 60 + s) * 1000);
}

/**
 * Format milliseconds → "hh:mm:ss.mmm"
 */
function msToTimeStr(ms) {
  if (ms < 0) ms = 0;
  const totalSec = Math.floor(ms / 1000);
  const millis   = ms % 1000;
  const s = totalSec % 60;
  const m = Math.floor(totalSec / 60) % 60;
  const h = Math.floor(totalSec / 3600);
  return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}.${String(millis).padStart(3,'0')}`;
}

/**
 * Format milliseconds → human readable "1 min 23 s 456 ms"
 */
function msToHuman(ms) {
  if (ms <= 0) return '0 ms';
  const h = Math.floor(ms / 3600000);
  const m = Math.floor((ms % 3600000) / 60000);
  const s = Math.floor((ms % 60000) / 1000);
  const millis = ms % 1000;
  const parts = [];
  if (h) parts.push(`${h} h`);
  if (m) parts.push(`${m} min`);
  if (s) parts.push(`${s} s`);
  if (millis) parts.push(`${millis} ms`);
  return parts.join(' ');
}

function showEl(el)  { el.classList.remove('hidden'); }
function hideEl(el)  { el.classList.add('hidden'); }
function setError(el, msg) { el.textContent = msg; showEl(el); }
function clearError(el)    { el.textContent = ''; hideEl(el); }

/* ── State ───────────────────────────────────────────────────────────────── */
let videoDurationMs = 0;

/* ── DOM refs ────────────────────────────────────────────────────────────── */
const ytUrlInput    = document.getElementById('yt-url');
const btnLoad       = document.getElementById('btn-load');
const urlError      = document.getElementById('url-error');

const cardSettings  = document.getElementById('card-settings');
const viThumb       = document.getElementById('vi-thumb');
const viTitle       = document.getElementById('vi-title');
const viDuration    = document.getElementById('vi-duration');

const startInput    = document.getElementById('start-time');
const endInput      = document.getElementById('end-time');
const cutLength     = document.getElementById('cut-length');
const durationPreview = document.getElementById('duration-preview');

const filenameInput = document.getElementById('filename');
const settingsError = document.getElementById('settings-error');
const btnDownload   = document.getElementById('btn-download');

const statusBar     = document.getElementById('status-bar');
const statusMsg     = document.getElementById('status-msg');

/* ── Load video info ─────────────────────────────────────────────────────── */
btnLoad.addEventListener('click', loadInfo);
ytUrlInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') loadInfo(); });

async function loadInfo() {
  clearError(urlError);
  const url = ytUrlInput.value.trim();
  if (!url) { setError(urlError, 'Bitte eine YouTube-URL eingeben.'); return; }

  setLoading(btnLoad, true);
  hideEl(cardSettings);

  try {
    const res = await fetch('/api/info', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });

    const data = await res.json();
    if (!res.ok) { setError(urlError, data.detail || 'Unbekannter Fehler.'); return; }

    // Populate info
    viTitle.textContent    = data.title;
    videoDurationMs        = data.duration_ms;
    viDuration.textContent = `Länge: ${msToHuman(data.duration_ms)}`;
    if (data.thumbnail) {
      viThumb.src = data.thumbnail;
      viThumb.style.display = 'block';
    } else {
      viThumb.style.display = 'none';
    }

    // Pre-fill times
    startInput.value = msToTimeStr(0);
    endInput.value   = msToTimeStr(data.duration_ms);

    // Pre-fill filename (sanitised title)
    const safeName = data.title.replace(/[^\w\s\-.()\u00C0-\u024F]/g, '').trim().slice(0, 80);
    filenameInput.value = safeName || 'audio';

    updateCutLength();
    showEl(cardSettings);
  } catch (err) {
    setError(urlError, `Netzwerkfehler: ${err.message}`);
  } finally {
    setLoading(btnLoad, false);
  }
}

/* ── Live cut-length update ──────────────────────────────────────────────── */
[startInput, endInput].forEach(inp => inp.addEventListener('input', updateCutLength));

function updateCutLength() {
  const startMs = parseTimeToMs(startInput.value);
  const endMs   = parseTimeToMs(endInput.value);
  if (isNaN(startMs) || isNaN(endMs) || endMs <= startMs) {
    cutLength.textContent = '–';
    return;
  }
  cutLength.textContent = msToHuman(endMs - startMs);
}

/* ── Download ────────────────────────────────────────────────────────────── */
btnDownload.addEventListener('click', startDownload);

async function startDownload() {
  clearError(settingsError);

  const url      = ytUrlInput.value.trim();
  const startMs  = parseTimeToMs(startInput.value);
  const endMs    = parseTimeToMs(endInput.value);
  const filename = filenameInput.value.trim() || 'audio';

  // Validate
  if (!url) { setError(settingsError, 'Keine URL vorhanden. Bitte erneut laden.'); return; }
  if (isNaN(startMs)) { setError(settingsError, 'Ungültige Startzeit.'); return; }
  if (isNaN(endMs))   { setError(settingsError, 'Ungültige Endzeit.'); return; }
  if (endMs <= startMs) { setError(settingsError, 'Die Endzeit muss nach der Startzeit liegen.'); return; }
  if (videoDurationMs > 0 && startMs >= videoDurationMs) {
    setError(settingsError, 'Startzeit liegt hinter der Videolänge.'); return;
  }

  setLoading(btnDownload, true);
  showStatusBar('Konvertierung läuft… Das kann je nach Videolänge etwas dauern.');

  try {
    const res = await fetch('/api/convert', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, start_ms: startMs, end_ms: endMs, filename }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Unbekannter Fehler.' }));
      setError(settingsError, err.detail || 'Fehler beim Konvertieren.');
      return;
    }

    // Trigger browser download
    const blob = await res.blob();
    const objUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = objUrl;
    a.download = `${filename}.mp3`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(objUrl);

    showStatusBar('Fertig! Download gestartet.', true);
  } catch (err) {
    setError(settingsError, `Netzwerkfehler: ${err.message}`);
    hideEl(statusBar);
  } finally {
    setLoading(btnDownload, false);
  }
}

/* ── UI helpers ──────────────────────────────────────────────────────────── */
function setLoading(btn, loading) {
  const text    = btn.querySelector('.btn-text');
  const spinner = btn.querySelector('.spinner');
  btn.disabled = loading;
  if (loading) { hideEl(text); showEl(spinner); }
  else         { showEl(text); hideEl(spinner); }
}

function showStatusBar(msg, done = false) {
  statusMsg.textContent = msg;
  const spinner = statusBar.querySelector('.spinner');
  if (done) { hideEl(spinner); }
  else      { showEl(spinner); }
  showEl(statusBar);
}
