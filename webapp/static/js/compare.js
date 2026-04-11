// compare.js — 비교 탭

import { api, uploadFile, initDropZone, setLoading, toast, overallChip, fmtDate } from './app.js';

let uploadedParsed = null;
let selectedTemplateId = null;

export function initCompare() {
  const zone  = document.getElementById('compare-drop-zone');
  const input = document.getElementById('compare-file-input');
  const runBtn = document.getElementById('compare-run-btn');
  const reportBtn = document.getElementById('compare-report-btn');

  initDropZone(zone, input, files => handleCompareUpload(files[0]));
  runBtn.addEventListener('click', runCompare);
  reportBtn.addEventListener('click', () => generateReport());

  document.getElementById('compare-template-select').addEventListener('change', e => {
    selectedTemplateId = e.target.value;
  });

  loadTemplateOptions();
  loadRecentResults();
}

async function loadTemplateOptions() {
  try {
    const templates = await api('/api/golden/templates');
    const sel = document.getElementById('compare-template-select');
    sel.innerHTML = `<option value="">— 자동 매칭 —</option>`;
    templates.forEach(t => {
      const opt = document.createElement('option');
      opt.value = t.id;
      opt.textContent = `${t.name}  [${t.hostname_regex || '모든 호스트'}]`;
      sel.appendChild(opt);
    });
  } catch {}
}

async function handleCompareUpload(file) {
  const zone = document.getElementById('compare-drop-zone');
  const osType = document.getElementById('compare-os-select').value;
  zone.innerHTML = `<div class="loading-overlay"><div class="spinner"></div><span>설정 분석 중... (${osType})</span></div>`;

  try {
    const data = await uploadFile(`/api/compare/upload?os=${osType}`, file);
    if (data.os) document.getElementById('compare-os-select').value = data.os;
    uploadedParsed = data.parsed;

    document.getElementById('compare-hostname').textContent = data.hostname || '(알 수 없음)';

    if (data.matched_template) {
      document.getElementById('compare-match-info').textContent =
        `자동 매칭: ${data.matched_template.name}`;
      document.getElementById('compare-template-select').value = data.matched_template.id;
      selectedTemplateId = data.matched_template.id;
    } else {
      document.getElementById('compare-match-info').textContent = '자동 매칭 없음 — 템플릿을 선택해주세요';
    }

    document.getElementById('compare-controls').style.display = 'flex';

    zone.innerHTML = `
      <div class="drop-icon">✅</div>
      <h3>${file.name}</h3>
      <p>업로드 완료 — 다른 파일을 올리려면 클릭</p>
    `;
  } catch (err) {
    zone.innerHTML = `
      <div class="drop-icon">📁</div>
      <h3>비교할 설정 파일을 드래그하거나 클릭</h3>
      <p>Cisco IOS / IOS-XE .cfg 파일 지원</p>
    `;
    toast(`업로드 실패: ${err.message}`, 'error');
  }
}

async function runCompare() {
  if (!uploadedParsed) return toast('먼저 파일을 업로드하세요.', 'error');
  const templateId = selectedTemplateId || document.getElementById('compare-template-select').value;
  if (!templateId) return toast('템플릿을 선택하세요.', 'error');

  const btn = document.getElementById('compare-run-btn');
  setLoading(btn, true, '비교 실행 중...');

  try {
    const result = await api('/api/compare/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ parsed: uploadedParsed, template_id: templateId, save: true }),
    });
    renderResult(result);
    document.getElementById('compare-report-btn').style.display = 'inline-flex';
    document.getElementById('compare-report-btn').dataset.hostname = result.hostname;
    loadRecentResults();
  } catch (err) {
    toast(`비교 실패: ${err.message}`, 'error');
  } finally {
    setLoading(btn, false);
  }
}

function renderResult(result) {
  const area = document.getElementById('compare-result-area');
  const overall = result.overall;
  const icons = { pass: '✅', review: '⚠️', fail: '❌' };

  const itemsHtml = result.items.map(item => `
    <div class="result-item ${item.status}">
      <span class="result-item-icon">${icons[item.status] || '?'}</span>
      <div>
        <div class="result-item-label">${item.label}</div>
        ${item.status !== 'pass'
          ? `<div class="result-item-msg">기대: <code>${item.expected}</code> / 실제: <code>${item.actual}</code> — ${item.message}</div>`
          : ''}
      </div>
      <span class="result-item-status ${item.status}">${item.status.toUpperCase()}</span>
    </div>
  `).join('');

  area.innerHTML = `
    <div class="result-header" style="background: var(--bg-card); border-color: var(--border);">
      <div class="result-badge ${overall}">${overall}</div>
      <div class="result-info">
        <div class="result-hostname">${result.hostname}</div>
        <div class="result-meta">템플릿: ${result.template_name} · ${result.passed_items}/${result.total_items} 항목 통과</div>
        <div class="score-bar mt-3">
          <div class="score-fill ${overall}" style="width: ${result.score}%"></div>
        </div>
      </div>
      <div style="font-size: 32px; font-weight: 800; color: var(--text-secondary)">${result.score}%</div>
    </div>
    <div class="result-items">${itemsHtml}</div>
  `;
  area.style.display = 'block';

  // 최신 결과 ID 저장 (레포트 생성용)
  area.dataset.latestResult = '';  // 다음 results 로드 후 채워짐
}

async function loadRecentResults() {
  try {
    const results = await api('/api/compare/results');
    const tbody = document.getElementById('compare-history-body');
    if (!results.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty-state">비교 이력 없음</td></tr>';
      return;
    }
    tbody.innerHTML = results.slice(0, 10).map(r => `
      <tr>
        <td><code>${r.hostname}</code></td>
        <td>${r.template_name}</td>
        <td>${overallChip(r.overall)}</td>
        <td>${r.score ?? '—'}%</td>
        <td>
          <button class="btn btn-sm btn-secondary" onclick="window.viewResult('${r.id}')">상세</button>
          <button class="btn btn-sm btn-secondary" onclick="window.reportResult('${r.id}', '${r.hostname}')">레포트</button>
        </td>
      </tr>
    `).join('');
  } catch {}
}

async function generateReport(resultId = null, hostname = null) {
  // resultId가 없으면 최신 결과 사용
  if (!resultId) {
    const results = await api('/api/compare/results').catch(() => []);
    if (!results.length) return toast('비교 결과가 없습니다.', 'error');
    resultId = results[0].id;
    hostname = results[0].hostname;
  }

  const useLlm = document.getElementById('compare-use-llm')?.checked ?? false;
  const btn = document.getElementById('compare-report-btn');
  if (btn) setLoading(btn, true, '레포트 생성 중...');

  try {
    const res = await api('/api/llm/report', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ result_id: resultId, use_llm: useLlm }),
    });

    // Report 탭으로 전달
    window.dispatchEvent(new CustomEvent('show-report', {
      detail: { report: res.report, hostname: res.hostname }
    }));

    // Report 탭 활성화
    document.querySelector('[data-tab="tab-report"]').click();
  } catch (err) {
    toast(`레포트 생성 실패: ${err.message}`, 'error');
  } finally {
    if (btn) setLoading(btn, false);
  }
}

// 전역 함수 등록
window.viewResult = async (id) => {
  try {
    const r = await api(`/api/compare/results/${id}`);
    renderResult({ ...r.detail, hostname: r.hostname, template_name: r.template_name });
    document.querySelector('[data-tab="tab-compare"]').click();
  } catch (err) {
    toast(`결과 조회 실패: ${err.message}`, 'error');
  }
};

window.reportResult = (id, hostname) => generateReport(id, hostname);
