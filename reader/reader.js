const chapterSelect = document.getElementById('chapterSelect');
const chapterTitle = document.getElementById('chapterTitle');
const chapterText = document.getElementById('chapterText');
const statusEl = document.getElementById('status');
const prevBtn = document.getElementById('prevBtn');
const nextBtn = document.getElementById('nextBtn');
const bottomPrev = document.getElementById('bottomPrev');
const bottomNext = document.getElementById('bottomNext');
const readToggle = document.getElementById('readToggle');
const markAllRead = document.getElementById('markAllRead');
const clearAllRead = document.getElementById('clearAllRead');
const fontSize = document.getElementById('fontSize');
const lineHeight = document.getElementById('lineHeight');
const contentWidth = document.getElementById('contentWidth');
const themeSelect = document.getElementById('themeSelect');

const SETTINGS_KEY = 'im_reader_settings_v1';
const READ_KEY = 'im_reader_read_v1';

let chapters = [];
let currentIndex = 0;
let readMap = {};

function setStatus(msg) {
  statusEl.textContent = msg;
}

function applySettings(settings) {
  document.documentElement.style.setProperty('--font-size', settings.fontSize + 'px');
  document.documentElement.style.setProperty('--line-height', settings.lineHeight);
  document.documentElement.style.setProperty('--content-width', settings.contentWidth + 'px');
  document.body.setAttribute('data-theme', settings.theme);
  fontSize.value = settings.fontSize;
  lineHeight.value = settings.lineHeight;
  contentWidth.value = settings.contentWidth;
  themeSelect.value = settings.theme;
}

function loadSettings() {
  const fallback = {
    fontSize: 20,
    lineHeight: 1.6,
    contentWidth: 760,
    theme: 'sepia'
  };
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (!raw) return fallback;
    return { ...fallback, ...JSON.parse(raw) };
  } catch {
    return fallback;
  }
}

function saveSettings(settings) {
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
}

function buildSelect() {
  chapterSelect.innerHTML = '';
  for (const [i, ch] of chapters.entries()) {
    const opt = document.createElement('option');
    opt.value = i;
    const title = ch.title ? ` - ${ch.title}` : '';
    const readMark = readMap[ch.num] ? ' ✓' : '';
    opt.textContent = `Chapter ${ch.num}${title}${readMark}`;
    chapterSelect.appendChild(opt);
  }
  if (Number.isFinite(currentIndex)) {
    chapterSelect.value = String(currentIndex);
  }
}

function loadReadMap() {
  try {
    const raw = localStorage.getItem(READ_KEY);
    if (!raw) return {};
    return JSON.parse(raw) || {};
  } catch {
    return {};
  }
}

function saveReadMap() {
  localStorage.setItem(READ_KEY, JSON.stringify(readMap));
}

function updateReadToggle() {
  const ch = chapters[currentIndex];
  if (!ch) return;
  readToggle.checked = !!readMap[ch.num];
}

function markRead(num, value) {
  if (value) readMap[num] = true;
  else delete readMap[num];
  saveReadMap();
  buildSelect();
  updateReadToggle();
}

function escapeHtml(s) {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function formatText(raw) {
  const lines = raw.split('\n');

  const htmlLines = lines.map((line, idx) => {
    const re = /“[^”]+”|\"[^\"]+\"/g;
    let out = '';
    let last = 0;
    let m;
    while ((m = re.exec(line)) !== null) {
      const qIdx = m.index;
      const qLen = m[0].length;
      out += escapeHtml(line.slice(last, qIdx));
      const quote = m[0];
      const open = quote[0];
      const close = quote[quote.length - 1];
      const inner = quote.slice(1, -1);
      const content = escapeHtml(inner);
      out += `${open}<strong class="quote">${content}</strong>${close}`;
      last = qIdx + qLen;
    }
    out += escapeHtml(line.slice(last));
    return out;
  });

  return htmlLines.join('<br>');
}

async function loadChapter(index, updateSelect = true) {
  if (index < 0 || index >= chapters.length) return;
  currentIndex = index;
  const ch = chapters[index];
  if (updateSelect) chapterSelect.value = String(index);
  setStatus(`Ładowanie: Chapter ${ch.num}...`);
  try {
    const res = await fetch('../' + ch.file);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const text = await res.text();
    chapterTitle.textContent = `Chapter ${ch.num}` + (ch.title ? ` - ${ch.title}` : '');
    chapterText.innerHTML = formatText(text.trim());
    setStatus(`Gotowe: Chapter ${ch.num}`);
    updateReadToggle();
    updateUrlHash();
  } catch (err) {
    chapterTitle.textContent = 'Błąd ładowania';
    chapterText.textContent = 'Nie udało się wczytać pliku. Upewnij się, że uruchomiłeś lokalny serwer HTTP w katalogu z plikami.';
    setStatus('Błąd: ' + err.message);
  }
}

function updateUrlHash() {
  const ch = chapters[currentIndex];
  if (!ch) return;
  const hash = `#${ch.num}`;
  if (location.hash !== hash) history.replaceState(null, '', hash);
}

function getIndexFromHash() {
  const n = parseInt(location.hash.replace('#', ''), 10);
  if (!Number.isFinite(n)) return 0;
  const idx = chapters.findIndex(c => c.num === n);
  return idx >= 0 ? idx : 0;
}

function wireControls() {
  prevBtn.addEventListener('click', () => loadChapter(currentIndex - 1));
  nextBtn.addEventListener('click', () => loadChapter(currentIndex + 1));
  if (bottomPrev) bottomPrev.addEventListener('click', () => loadChapter(currentIndex - 1));
  if (bottomNext) bottomNext.addEventListener('click', () => loadChapter(currentIndex + 1));
  chapterSelect.addEventListener('change', (e) => loadChapter(parseInt(e.target.value, 10)));
  readToggle.addEventListener('change', () => {
    const ch = chapters[currentIndex];
    if (!ch) return;
    markRead(ch.num, readToggle.checked);
  });
  markAllRead.addEventListener('click', () => {
    for (const ch of chapters) readMap[ch.num] = true;
    saveReadMap();
    buildSelect();
    updateReadToggle();
  });
  clearAllRead.addEventListener('click', () => {
    readMap = {};
    saveReadMap();
    buildSelect();
    updateReadToggle();
  });

  const settings = loadSettings();
  applySettings(settings);

  fontSize.addEventListener('input', () => {
    settings.fontSize = parseInt(fontSize.value, 10);
    applySettings(settings);
    saveSettings(settings);
  });

  lineHeight.addEventListener('input', () => {
    settings.lineHeight = parseFloat(lineHeight.value);
    applySettings(settings);
    saveSettings(settings);
  });

  contentWidth.addEventListener('input', () => {
    settings.contentWidth = parseInt(contentWidth.value, 10);
    applySettings(settings);
    saveSettings(settings);
  });

  themeSelect.addEventListener('change', () => {
    settings.theme = themeSelect.value;
    applySettings(settings);
    saveSettings(settings);
  });

  window.addEventListener('keydown', (e) => {
    if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT')) return;
    if (e.key === 'ArrowLeft') loadChapter(currentIndex - 1);
    if (e.key === 'ArrowRight') loadChapter(currentIndex + 1);
    if (e.key === '[') {
      settings.fontSize = Math.max(16, settings.fontSize - 1);
      applySettings(settings);
      saveSettings(settings);
    }
    if (e.key === ']') {
      settings.fontSize = Math.min(28, settings.fontSize + 1);
      applySettings(settings);
      saveSettings(settings);
    }
    if (e.key === '{') {
      settings.lineHeight = Math.max(1.2, Math.round((settings.lineHeight - 0.05) * 100) / 100);
      applySettings(settings);
      saveSettings(settings);
    }
    if (e.key === '}') {
      settings.lineHeight = Math.min(2.0, Math.round((settings.lineHeight + 0.05) * 100) / 100);
      applySettings(settings);
      saveSettings(settings);
    }
  });
}

async function init() {
  setStatus('Wczytywanie listy rozdziałów...');
  try {
    const res = await fetch('chapters.json');
    if (!res.ok) throw new Error('HTTP ' + res.status);
    chapters = await res.json();
    readMap = loadReadMap();
    buildSelect();
    wireControls();
    const startIndex = getIndexFromHash();
    await loadChapter(startIndex);
  } catch (err) {
    chapterTitle.textContent = 'Błąd inicjalizacji';
    chapterText.textContent = 'Nie udało się wczytać listy rozdziałów.';
    setStatus('Błąd: ' + err.message);
  }
}

init();
