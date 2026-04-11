// app.js — 공통 유틸리티 및 상태 관리

// ── Toast 알림 ──────────────────────────────────────────────────────────
const toastContainer = document.getElementById('toast-container');

export function toast(msg, type = 'info', duration = 3500) {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  toastContainer.appendChild(el);
  setTimeout(() => el.remove(), duration);
}

// ── API 헬퍼 ────────────────────────────────────────────────────────────
export async function api(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || '요청 실패');
  }
  return res.json();
}

export async function uploadFile(path, file, fieldName = 'file') {
  const fd = new FormData();
  fd.append(fieldName, file);
  return api(path, { method: 'POST', body: fd });
}

export async function uploadFiles(path, files, fieldName = 'files') {
  const fd = new FormData();
  for (const f of files) fd.append(fieldName, f);
  return api(path, { method: 'POST', body: fd });
}

// ── 탭 전환 ─────────────────────────────────────────────────────────────
export function initTabs() {
  document.querySelectorAll('.nav-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      tab.classList.add('active');
      document.getElementById(tab.dataset.tab).classList.add('active');
    });
  });
}

// ── 드롭존 ──────────────────────────────────────────────────────────────
export function initDropZone(zoneEl, inputEl, onFiles) {
  zoneEl.addEventListener('click', () => inputEl.click());
  zoneEl.addEventListener('dragover', e => { e.preventDefault(); zoneEl.classList.add('drag-over'); });
  zoneEl.addEventListener('dragleave', () => zoneEl.classList.remove('drag-over'));
  zoneEl.addEventListener('drop', e => {
    e.preventDefault();
    zoneEl.classList.remove('drag-over');
    onFiles([...e.dataTransfer.files]);
  });
  inputEl.addEventListener('change', () => { if (inputEl.files.length) onFiles([...inputEl.files]); });
}

// ── 로딩 상태 ────────────────────────────────────────────────────────────
export function setLoading(el, isLoading, label = '처리 중...') {
  if (isLoading) {
    el.dataset.originalHtml = el.innerHTML;
    el.innerHTML = `<span class="spinner"></span> ${label}`;
    el.disabled = true;
  } else {
    el.innerHTML = el.dataset.originalHtml || el.innerHTML;
    el.disabled = false;
  }
}

// ── 판정 뱃지 ────────────────────────────────────────────────────────────
export function overallChip(overall) {
  const icons = { Pass: '✅', Review: '⚠️', Fail: '❌', Skipped: '—' };
  const cls = overall?.toLowerCase() || 'skip';
  return `<span class="chip ${cls}">${icons[overall] || ''} ${overall || 'N/A'}</span>`;
}

// ── 날짜 포맷 ────────────────────────────────────────────────────────────
export function fmtDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('ko-KR', { dateStyle: 'short', timeStyle: 'short' });
}

// ── 클립보드 복사 ─────────────────────────────────────────────────────────
export async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast('클립보드에 복사됨', 'success');
  } catch {
    toast('복사 실패', 'error');
  }
}
