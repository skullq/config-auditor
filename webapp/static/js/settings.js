// settings.js — Ollama 설정 탭 및 레포트 탭

import { api, toast, copyToClipboard } from './app.js';

export function initSettings() {
  loadSettings();
  document.getElementById('settings-save-btn').addEventListener('click', saveSettings);
  document.getElementById('settings-test-btn').addEventListener('click', testOllama);
  document.getElementById('settings-model-refresh').addEventListener('click', loadModels);
}

export function initReport() {
  // 다른 탭에서 레포트 이벤트 수신
  window.addEventListener('show-report', e => {
    renderReport(e.detail.report, e.detail.hostname);
  });

  document.getElementById('report-copy-btn').addEventListener('click', () => {
    const text = document.getElementById('report-output').textContent;
    copyToClipboard(text);
  });

  document.getElementById('report-download-btn').addEventListener('click', () => {
    const text = document.getElementById('report-output').textContent;
    const hostname = document.getElementById('report-hostname').textContent;
    const blob = new Blob([text], { type: 'text/markdown' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `audit_${hostname || 'report'}.md`;
    a.click();
  });
}

function renderReport(markdown, hostname) {
  document.getElementById('report-hostname').textContent = hostname || '';
  document.getElementById('report-output').textContent = markdown;
  document.getElementById('report-actions').style.display = 'flex';
}

async function loadSettings() {
  try {
    const s = await api('/api/llm/settings');
    document.getElementById('settings-ollama-url').value = s.ollama_url || 'http://localhost:11434';
    document.getElementById('settings-prompt').value = s.prompt_template || '';
    await loadModels(s.ollama_url, s.model);
  } catch {}
}

async function loadModels(url, selectedModel) {
  if (typeof url !== 'string') url = document.getElementById('settings-ollama-url').value;
  const sel = document.getElementById('settings-model-select');
  const indicator = document.getElementById('settings-ollama-status');
  sel.innerHTML = '<option>불러오는 중...</option>';

  try {
    const data = await api('/api/llm/models');
    if (!data.available) {
      sel.innerHTML = '<option value="">Ollama 연결 불가</option>';
      indicator.innerHTML = '🔴 Ollama 오프라인';
      indicator.style.color = 'var(--fail)';
      return;
    }
    indicator.innerHTML = '🟢 Ollama 연결됨';
    indicator.style.color = 'var(--pass)';
    sel.innerHTML = data.models.map(m =>
      `<option value="${m}" ${m === selectedModel ? 'selected' : ''}>${m}</option>`
    ).join('');
    if (!data.models.length) {
      sel.innerHTML = '<option value="">모델 없음 (ollama pull 필요)</option>';
    }
  } catch {
    sel.innerHTML = '<option value="">오류</option>';
    indicator.innerHTML = '🔴 연결 오류';
    indicator.style.color = 'var(--fail)';
  }
}

async function testOllama() {
  const url = document.getElementById('settings-ollama-url').value;
  await loadModels(url);
}

async function saveSettings() {
  const ollama_url = document.getElementById('settings-ollama-url').value.trim();
  const model = document.getElementById('settings-model-select').value;
  const prompt_template = document.getElementById('settings-prompt').value;

  try {
    await api('/api/llm/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ollama_url, model, prompt_template }),
    });
    toast('설정 저장 완료', 'success');
  } catch (err) {
    toast(`저장 실패: ${err.message}`, 'error');
  }
}
