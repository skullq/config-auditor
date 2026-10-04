// settings.js — Ollama 설정 탭 및 레포트 탭

import { api, toast, copyToClipboard } from './app.js';

export function initSettings() {
  loadSettings();
  loadSecurityRules();
  document.getElementById('settings-save-btn').addEventListener('click', saveSettings);
  document.getElementById('settings-test-btn').addEventListener('click', testOllama);
  document.getElementById('settings-model-refresh').addEventListener('click', loadModels);
  document.getElementById('settings-wipe-btn').addEventListener('click', wipeDatabase);

  const reloadRulesBtn = document.getElementById('security-rules-reload-btn');
  if (reloadRulesBtn) reloadRulesBtn.addEventListener('click', reloadSecurityRules);

  const importSeedsBtn = document.getElementById('security-seeds-import-btn');
  if (importSeedsBtn) importSeedsBtn.addEventListener('click', importSeedTemplates);

  const exportSeedsBtn = document.getElementById('security-seeds-export-btn');
  if (exportSeedsBtn) exportSeedsBtn.addEventListener('click', exportTemplateToSeed);
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

// ── 선언적 보안 정책 및 Git-Ops Seed 관리 ────────────────────────────

async function loadSecurityRules() {
  const tbody = document.getElementById('security-rules-tbody');
  const countEl = document.getElementById('security-rules-count');
  if (!tbody) return;

  try {
    const rules = await api('/api/security/rules');
    if (countEl) countEl.textContent = rules.length;

    if (!rules.length) {
      tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding:12px;" class="text-muted">등록된 보안 규칙이 없습니다.</td></tr>';
      return;
    }

    tbody.innerHTML = rules.map(r => {
      const badgeClass = r.level === 'danger' ? 'chip-fail' : (r.level === 'warning' ? 'chip-review' : 'chip-pass');
      return `
        <tr>
          <td><span class="chip ${badgeClass}" style="font-size:10px; padding:1px 6px;">${(r.level || 'info').toUpperCase()}</span></td>
          <td style="color:var(--text-secondary); font-family:monospace;">${r.standard || 'CIS / DISA'}</td>
          <td style="font-weight:600; color:var(--text-primary);">${r.title || ''}</td>
          <td><code style="font-size:10px; background:rgba(0,0,0,0.3); padding:2px 4px; border-radius:3px;">${r.pattern || ''}</code></td>
          <td class="text-muted" style="font-size:11px;">${r.reason || ''}</td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    console.error('loadSecurityRules error:', err);
    tbody.innerHTML = `<tr><td colspan="5" style="color:var(--danger); text-align:center;">규칙 로드 실패: ${err.message}</td></tr>`;
  }
}

async function reloadSecurityRules() {
  const btn = document.getElementById('security-rules-reload-btn');
  try {
    if (btn) btn.disabled = true;
    const res = await api('/api/security/rules/reload', { method: 'POST' });
    toast(res.message, 'success');
    await loadSecurityRules();
  } catch (err) {
    toast(`동기화 실패: ${err.message}`, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function importSeedTemplates() {
  const btn = document.getElementById('security-seeds-import-btn');
  try {
    if (btn) btn.disabled = true;
    const res = await api('/api/security/templates/import-seeds', { method: 'POST' });
    toast(res.message, 'success');
    if (window.loadGoldenTemplates) window.loadGoldenTemplates();
    if (window.loadCompareTree) window.loadCompareTree();
  } catch (err) {
    toast(`Seed 가져오기 실패: ${err.message}`, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function exportTemplateToSeed() {
  try {
    const tpls = await api('/api/golden/templates');
    if (!tpls.length) {
      return toast('내보낼 등록된 골든 템플릿이 없습니다.', 'error');
    }

    const tplListStr = tpls.map((t, idx) => `${idx + 1}. ${t.name} (ID: ${t.id})`).join('\n');
    const input = prompt(`Git Seed 파일로 내보낼 템플릿 번호를 입력하세요:\n\n${tplListStr}\n\n번호 입력 (1~${tpls.length}):`);
    if (!input) return;

    const selectedIdx = parseInt(input.trim(), 10) - 1;
    if (isNaN(selectedIdx) || selectedIdx < 0 || selectedIdx >= tpls.length) {
      return toast('올바른 번호를 입력하세요.', 'error');
    }

    const targetTpl = tpls[selectedIdx];
    const res = await api('/api/security/templates/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ template_id: targetTpl.id })
    });

    toast(`"${targetTpl.name}" 템플릿이 ${res.path} 파일로 내보내기 되었습니다. (Git 커밋 가능)`, 'success');
  } catch (err) {
    toast(`내보내기 실패: ${err.message}`, 'error');
  }
}

