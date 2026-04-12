// settings.js — Ollama 설정 탭 및 레포트 탭

import { api, toast, copyToClipboard } from './app.js';

export function initSettings() {
  loadSettings();
  document.getElementById('settings-save-btn').addEventListener('click', saveSettings);
  document.getElementById('settings-test-btn').addEventListener('click', testOllama);
  document.getElementById('settings-model-refresh').addEventListener('click', loadModels);
  document.getElementById('settings-wipe-btn').addEventListener('click', wipeDatabase);
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

async function wipeDatabase() {
  if (!confirm('정말 모든 데이터(골든 템플릿, 비교 이력)를 삭제하시겠습니까? (설정 제외) 이 작업은 되돌릴 수 없습니다.')) return;
  
  try {
    const res = await api('/api/settings/reset', { method: 'POST' });
    toast(res.message, 'success');
    window.location.reload(); // Refresh to clean states
  } catch (err) {
    toast(`초기화 실패: ${err.message}`, 'error');
  }
}
