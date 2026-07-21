/* ── Helpers ─────────────────────────────────────────────────────────────── */

function showEl(el)  { el.classList.remove('hidden'); }
function hideEl(el)  { el.classList.add('hidden'); }
function setError(el, msg) { el.textContent = msg; showEl(el); }
function clearError(el)    { el.textContent = ''; hideEl(el); }

function msToHuman(ms) {
  if (ms <= 0) return '0 ms';
  const h = Math.floor(ms / 3600000);
  const m = Math.floor((ms % 3600000) / 60000);
  const s = Math.floor((ms % 60000) / 1000);
  const mil = ms % 1000;
  const parts = [];
  if (h)   parts.push(`${h} h`);
  if (m)   parts.push(`${m} min`);
  if (s)   parts.push(`${s} s`);
  if (mil) parts.push(`${mil} ms`);
  return parts.join(' ');
}

/** ms (integer) → "mm:ss.mmm" */
function msToTimeStr(ms) {
  if (ms < 0) ms = 0;
  const m   = Math.floor(ms / 60000);
  const s   = Math.floor((ms % 60000) / 1000);
  const mil = ms % 1000;
  return `${p2(m)}:${p2(s)}.${p3(mil)}`;
}
function p2(n) { return String(n).padStart(2, '0'); }
function p3(n) { return String(n).padStart(3, '0'); }

/**
 * Parse "mm:ss.mmm" | "ss.mmm" | bare number → ms.
 * Returns NaN on bad input.
 */
function parseTimeToMs(str) {
  if (!str || !str.trim()) return NaN;
  str = str.trim();
  const parts = str.split(':');
  let m = 0, s = 0;
  if (parts.length >= 2) { m = +parts[parts.length - 2]; s = parseFloat(parts[parts.length - 1]); }
  else                   { s = parseFloat(parts[0]); }
  if ([m, s].some(v => isNaN(v))) return NaN;
  return Math.round((m * 60 + s) * 1000);
}

/* ── State ───────────────────────────────────────────────────────────────── */
let videoDurationMs = 0;
let previewToken    = null;
let audioEl         = null;
let isSeeking       = false;

/* ── DOM refs ────────────────────────────────────────────────────────────── */
const ytUrlInput     = document.getElementById('yt-url');
const btnLoad        = document.getElementById('btn-load');
const urlError       = document.getElementById('url-error');

const cardSettings   = document.getElementById('card-settings');
const viThumb        = document.getElementById('vi-thumb');
const viTitle        = document.getElementById('vi-title');
const viDuration     = document.getElementById('vi-duration');

const playerLoading  = document.getElementById('player-loading');
const playerCard     = document.getElementById('player-card');
const cutEditor      = document.getElementById('cut-editor');

const timeCurrent    = document.getElementById('time-current');
const timeTotal      = document.getElementById('time-total');
const progressSlider = document.getElementById('progress-slider');
const btnPlay        = document.getElementById('btn-play');
const playIcon       = document.getElementById('play-icon');
const volumeSlider   = document.getElementById('volume-slider');

const overallStart   = document.getElementById('overall-start');
const overallEnd     = document.getElementById('overall-end');
const cutList        = document.getElementById('cut-list');
const btnAddCut      = document.getElementById('btn-add-cut');

const filenameInput  = document.getElementById('filename');
const settingsError  = document.getElementById('settings-error');
const btnDownload    = document.getElementById('btn-download');

const statusBar      = document.getElementById('status-bar');
const statusMsg      = document.getElementById('status-msg');

/* ── Load video info ─────────────────────────────────────────────────────── */
btnLoad.addEventListener('click', loadInfo);
ytUrlInput.addEventListener('keydown', e => { if (e.key === 'Enter') loadInfo(); });

async function loadInfo() {
  clearError(urlError);
  const url = ytUrlInput.value.trim();
  if (!url) { setError(urlError, 'Bitte eine YouTube-URL eingeben.'); return; }

  setLoading(btnLoad, true);
  hideEl(cardSettings);
  previewToken = null;

  if (audioEl) { audioEl.pause(); audioEl.removeAttribute('src'); audioEl.load(); }

  try {
    const res  = await fetch('/api/info', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();
    if (!res.ok) { setError(urlError, data.detail || 'Unbekannter Fehler.'); return; }

    viTitle.textContent    = data.title;
    videoDurationMs        = data.duration_ms;
    viDuration.textContent = `Länge: ${msToHuman(data.duration_ms)}`;
    viThumb.style.display  = data.thumbnail ? 'block' : 'none';
    if (data.thumbnail) viThumb.src = data.thumbnail;

    const safeName = data.title.replace(/[^\w\s\-.()\u00C0-\u024F]/g, '').trim().slice(0, 80);
    filenameInput.value = safeName || 'audio';

    // Reset player loading
    playerLoading.innerHTML =
      '<span class="spinner"></span><span>Audio wird heruntergeladen\u2026</span>';
    showEl(playerLoading);
    hideEl(playerCard);
    hideEl(cutEditor);
    btnDownload.disabled = true;
    cutList.innerHTML = '';
    showEl(cardSettings);

    loadPreview(url);
  } catch (err) {
    setError(urlError, `Netzwerkfehler: ${err.message}`);
  } finally {
    setLoading(btnLoad, false);
  }
}

/* ── Download audio preview ──────────────────────────────────────────────── */
async function loadPreview(url) {
  try {
    const res  = await fetch('/api/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();
    if (!res.ok) {
      playerLoading.innerHTML =
        `<span class="player-error">\u26a0 Audio konnte nicht geladen werden: ${data.detail || 'Fehler'}</span>`;
      return;
    }
    previewToken = data.token;
    initAudioPlayer(previewToken);
  } catch (err) {
    playerLoading.innerHTML =
      `<span class="player-error">\u26a0 Netzwerkfehler: ${err.message}</span>`;
  }
}

/* ── Audio player ────────────────────────────────────────────────────────── */
function initAudioPlayer(token) {
  audioEl = document.getElementById('audio-el');
  audioEl.volume = parseFloat(volumeSlider.value);
  audioEl.src    = `/api/audio/${token}`;

  audioEl.addEventListener('loadedmetadata', onMetaLoaded, { once: true });
  audioEl.addEventListener('error', () => {
    playerLoading.innerHTML =
      '<span class="player-error">\u26a0 Audio konnte nicht geladen werden.</span>';
    showEl(playerLoading);
  }, { once: true });
}

function onMetaLoaded() {
  const durMs = Math.round(audioEl.duration * 1000);
  progressSlider.max   = durMs;
  progressSlider.value = 0;
  timeTotal.textContent   = msToTimeStr(durMs);
  timeCurrent.textContent = msToTimeStr(0);

  overallStart.value = msToTimeStr(0);
  overallEnd.value   = msToTimeStr(durMs);

  hideEl(playerLoading);
  showEl(playerCard);
  showEl(cutEditor);
  btnDownload.disabled = false;

  // timeupdate
  audioEl.addEventListener('timeupdate', () => {
    if (isSeeking) return;
    const ms = Math.round(audioEl.currentTime * 1000);
    timeCurrent.textContent = msToTimeStr(ms);
    progressSlider.value    = ms;
  });

  audioEl.addEventListener('ended', () => {
    playIcon.textContent = '\u25b6';
  });
}

/* ── Transport buttons ───────────────────────────────────────────────────── */
btnPlay.addEventListener('click', () => {
  if (!audioEl || !audioEl.src) return;
  if (audioEl.paused) {
    audioEl.play();
    playIcon.textContent = '\u23f8';
  } else {
    audioEl.pause();
    playIcon.textContent = '\u25b6';
  }
});

document.getElementById('btn-seek-back10').addEventListener('click', () => seekBy(-10000));
document.getElementById('btn-seek-back1' ).addEventListener('click', () => seekBy(-1000));
document.getElementById('btn-seek-fwd1'  ).addEventListener('click', () => seekBy(1000));
document.getElementById('btn-seek-fwd10' ).addEventListener('click', () => seekBy(10000));

function seekBy(deltaMs) {
  if (!audioEl || !audioEl.duration) return;
  const durMs  = Math.round(audioEl.duration * 1000);
  const newMs  = Math.max(0, Math.min(Math.round(audioEl.currentTime * 1000) + deltaMs, durMs));
  audioEl.currentTime     = newMs / 1000;
  timeCurrent.textContent = msToTimeStr(newMs);
  progressSlider.value    = newMs;
}

/* ── Progress slider ─────────────────────────────────────────────────────── */
progressSlider.addEventListener('mousedown',  () => { isSeeking = true; });
progressSlider.addEventListener('touchstart', () => { isSeeking = true; }, { passive: true });

progressSlider.addEventListener('input', () => {
  const ms = parseInt(progressSlider.value, 10);
  timeCurrent.textContent = msToTimeStr(ms);
});

function commitSeek() {
  isSeeking = false;
  if (!audioEl || !audioEl.duration) return;
  audioEl.currentTime = parseInt(progressSlider.value, 10) / 1000;
}
progressSlider.addEventListener('mouseup',  commitSeek);
progressSlider.addEventListener('touchend', commitSeek);
progressSlider.addEventListener('change',   commitSeek);

/* ── Volume ──────────────────────────────────────────────────────────────── */
volumeSlider.addEventListener('input', () => {
  if (audioEl) audioEl.volume = parseFloat(volumeSlider.value);
});

/* ── Cut rows ────────────────────────────────────────────────────────────── */
let cutRowCount = 0;

btnAddCut.addEventListener('click', addCutRow);

function addCutRow() {
  const id  = ++cutRowCount;
  const row = document.createElement('div');
  row.className = 'cut-row';
  row.id = `cut-row-${id}`;

  const label = document.createElement('span');
  label.className   = 'cut-index';
  label.textContent = `#${id}`;

  const makeField = (lbl, cls, pholder) => {
    const grp   = document.createElement('div');
    grp.className = 'form-group cut-field';
    const l   = document.createElement('label');
    l.textContent = lbl;
    const inp = document.createElement('input');
    inp.type        = 'text';
    inp.className   = `time-input ${cls}`;
    inp.placeholder = pholder;
    grp.appendChild(l);
    grp.appendChild(inp);
    return grp;
  };

  const removeBtn = document.createElement('button');
  removeBtn.className   = 'btn-remove-cut';
  removeBtn.title       = 'Entfernen';
  removeBtn.textContent = '\u2715';
  removeBtn.addEventListener('click', () => row.remove());

  row.appendChild(label);
  row.appendChild(makeField('Von', 'cut-from', '00:00.000'));
  row.appendChild(makeField('Bis', 'cut-to',   '00:00.000'));
  row.appendChild(removeBtn);
  cutList.appendChild(row);
}

/* ── Compute keep-segments ───────────────────────────────────────────────── */
function computeKeepSegments() {
  const startMs = parseTimeToMs(overallStart.value);
  const endMs   = parseTimeToMs(overallEnd.value);

  if (isNaN(startMs)) throw 'Gesamt-Start: ung\u00fcltiges Zeitformat.';
  if (isNaN(endMs))   throw 'Gesamt-Ende: ung\u00fcltiges Zeitformat.';
  if (endMs <= startMs) throw 'Gesamt-Ende muss nach dem Gesamt-Start liegen.';

  const rows    = [...cutList.querySelectorAll('.cut-row')];
  const deletes = [];
  for (const row of rows) {
    const fromMs = parseTimeToMs(row.querySelector('.cut-from').value);
    const toMs   = parseTimeToMs(row.querySelector('.cut-to').value);
    if (isNaN(fromMs) || isNaN(toMs)) throw 'Ausschnitt: ein Zeitfeld ist leer oder ung\u00fcltig.';
    if (toMs <= fromMs) throw 'Ausschnitt: Bis-Zeit muss nach Von-Zeit liegen.';
    const cs = Math.max(fromMs, startMs);
    const ce = Math.min(toMs,   endMs);
    if (ce > cs) deletes.push({ s: cs, e: ce });
  }

  // Merge overlapping deletes
  deletes.sort((a, b) => a.s - b.s);
  const merged = [];
  for (const d of deletes) {
    if (merged.length && d.s <= merged[merged.length - 1].e) {
      merged[merged.length - 1].e = Math.max(merged[merged.length - 1].e, d.e);
    } else {
      merged.push({ ...d });
    }
  }

  // Build keep list
  const keeps  = [];
  let cursor   = startMs;
  for (const d of merged) {
    if (d.s > cursor + 1) keeps.push({ start_ms: cursor, end_ms: d.s });
    cursor = Math.max(cursor, d.e);
  }
  if (cursor < endMs - 1) keeps.push({ start_ms: cursor, end_ms: endMs });

  if (keeps.length === 0) throw 'Kein Audio \u00fcbrig \u2013 der gesamte Bereich wurde rausgeschnitten.';
  return keeps;
}

/* ── Download ────────────────────────────────────────────────────────────── */
btnDownload.addEventListener('click', startDownload);

async function startDownload() {
  clearError(settingsError);

  if (!previewToken) {
    setError(settingsError, 'Audio noch nicht geladen. Bitte warten.');
    return;
  }

  let keeps;
  try {
    keeps = computeKeepSegments();
  } catch (msg) {
    setError(settingsError, msg);
    return;
  }

  const filename = filenameInput.value.trim() || 'audio';

  setLoading(btnDownload, true);
  showStatusBar('Konvertierung l\u00e4uft\u2026');

  try {
    const res = await fetch('/api/convert', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: previewToken, segments: keeps, filename }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Unbekannter Fehler.' }));
      setError(settingsError, err.detail || 'Fehler beim Konvertieren.');
      return;
    }

    const blob   = await res.blob();
    const objUrl = URL.createObjectURL(blob);
    const a      = document.createElement('a');
    a.href       = objUrl;
    a.download   = `${filename}.mp3`;
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
  btn.disabled = loading;
  const text    = btn.querySelector('.btn-text');
  const spinner = btn.querySelector('.spinner');
  if (!text || !spinner) return;
  if (loading) { hideEl(text); showEl(spinner); }
  else         { showEl(text); hideEl(spinner); }
}

function showStatusBar(msg, done = false) {
  statusMsg.textContent = msg;
  const sp = statusBar.querySelector('.spinner');
  if (done) hideEl(sp); else showEl(sp);
  showEl(statusBar);
}
