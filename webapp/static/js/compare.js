// compare.js — 비교 탭

import { api, uploadFile, initDropZone, toast, overallChip, fmtDate, setLoading } from './app.js';

let pendingCompareQueue = [];

export function initCompare() {
  const zone  = document.getElementById('compare-drop-zone');
  const input = document.getElementById('compare-file-input');

  // Load templates on click
  document.querySelector('[data-tab="tab-compare"]').addEventListener('click', loadCompareTemplates);
  loadCompareTemplates();

  initDropZone(zone, input, (files) => {
    if (files.length === 0) return;
    
    const tbody = document.getElementById('compare-history-body');
    const emptyState = tbody.querySelector('.empty-state');
    if (emptyState) tbody.innerHTML = '';
    
    files.forEach(f => {
      pendingCompareQueue.push(f);
      const tr = document.createElement('tr');
      tr.id = 'queue-' + f.name.replace(/[^a-zA-Z0-9]/g, '');
      tr.innerHTML = `
        <td><strong>${f.name}</strong><br><small style="color:var(--text-muted)">대기 중...</small></td>
        <td>-</td>
        <td><div style="font-size:12px;color:var(--text-muted)">⏳ 실행 대기</div></td>
        <td>-</td>
        <td>-</td>
        <td>-</td>
      `;
      tbody.insertBefore(tr, tbody.firstChild);
    });
    
    toast(`${files.length}개 파일이 대기열에 추가되었습니다.`, 'info');
  });

  document.getElementById('compare-run-btn').addEventListener('click', executeCompareQueue);
  document.getElementById('compare-clear-btn').addEventListener('click', () => {
    pendingCompareQueue = [];
    document.getElementById('compare-history-body').innerHTML = '<tr><td colspan="5" class="empty-state">파일을 업로드하면 순차적으로 진행됩니다.</td></tr>';
    document.getElementById('compare-result-area').style.display = 'none';
  });
}

async function loadCompareTemplates() {
  try {
    const res = await fetch('/api/golden/templates?_=' + Date.now());
    const templates = await res.json();
    const sel = document.getElementById('compare-template-select');
    sel.innerHTML = '<option value="auto" selected>자동 매칭 (Hostname 기반)</option>';
    templates.forEach(t => {
       sel.innerHTML += `<option value="${t.id}">${t.name}</option>`;
    });
  } catch(e) {}
}

async function executeCompareQueue() {
  if (pendingCompareQueue.length === 0) {
    toast('대기열에 실행할 파일이 없습니다.', 'warning');
    return;
  }
  
  const filesToRun = [...pendingCompareQueue];
  pendingCompareQueue = []; // 큐 초기화 (다음 드롭을 위해)
  
  toast(`${filesToRun.length}개 파일 비교 시작`, 'info');
  for (let i = 0; i < filesToRun.length; i++) {
      await processSingleFile(filesToRun[i]);
  }
  toast(`비교 실행 완료`, 'success');
}


async function checkDuplicate(hostname) {
  try {
     const res = await api(`/api/compare/check_duplicate?hostname=${encodeURIComponent(hostname)}`);
     return res.exists;
  } catch(e) {
     return false;
  }
}

async function processSingleFile(file) {
  const tbody = document.getElementById('compare-history-body');
  const tr = document.createElement('tr');
  const rowId = 'row-' + Date.now() + Math.random().toString(36).substr(2, 5);
  tr.id = rowId;
  
  tr.innerHTML = `
    <td><strong>${file.name}</strong><br><small style="color:var(--text-muted)">Hostname: (확인 중...)</small></td>
    <td>-</td>
    <td><div class="spinner" style="width:14px;height:14px;display:inline-block"></div> 1/4 파싱 및 분석 중...</td>
    <td>-</td>
    <td>-</td>
    <td>-</td>
  `;
  // 기존 대기 UI 교체
  const qId = 'queue-' + file.name.replace(/[^a-zA-Z0-9]/g, '');
  const existingTr = document.getElementById(qId);
  if (existingTr) existingTr.replaceWith(tr);
  else tbody.insertBefore(tr, tbody.firstChild);

  const osType = document.getElementById('compare-os-select').value;
  const targetTpl = document.getElementById('compare-template-select').value;
  
  try {
    // 1. Upload & Parsing
    const data = await uploadFile(`/api/compare/upload?os=${osType}`, file);
    const hostname = data.hostname || file.name;
    
    tr.children[0].innerHTML = `<strong>${file.name}</strong><br><small style="color:var(--text-muted)">Hostname: <code>${hostname}</code></small>`;
    tr.children[2].innerHTML = `<div class="spinner" style="width:14px;height:14px;display:inline-block"></div> 2/4 템플릿 매칭 중...`;
    
    // 2. Template matching check
    let matchedTemplateId = null;
    let matchedTemplateName = null;
    
    if (targetTpl === 'auto') {
      if (!data.matched_template) {
         tr.children[1].innerHTML = `<span style="color:var(--danger)">자동 매칭 템플릿 없음</span>`;
         tr.children[2].innerHTML = `❌ 오류`;
         tr.children[3].textContent = 'Skipped';
         return;
      }
      matchedTemplateId = data.matched_template.id;
      matchedTemplateName = data.matched_template.name;
    } else {
      matchedTemplateId = targetTpl;
      matchedTemplateName = document.getElementById('compare-template-select').options[document.getElementById('compare-template-select').selectedIndex].text;
    }
    
    tr.children[1].textContent = matchedTemplateName;
    tr.children[2].innerHTML = `<div class="spinner" style="width:14px;height:14px;display:inline-block"></div> 3/4 골든 컨피그와 비교 중...`;
    
    // 3. Duplicate check for LLM Report warning
    const isDup = await checkDuplicate(hostname);
    if (isDup) {
       toast(`[${hostname}] 기존 결과가 존재합니다. LLM 레포트 재생성이 필요할 수 있습니다.`, 'warning');
    }
    
    // 4. Run compare
    const result = await api('/api/compare/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ parsed: data.parsed, template_id: matchedTemplateId, save: true }),
    });
    
    // 5. Update row
    tr.children[2].innerHTML = `✅ 4/4 비교 완료`;
    tr.children[3].innerHTML = overallChip(result.overall);
    tr.children[4].textContent = `${result.score}%`;
    tr.children[5].innerHTML = `<button class="btn btn-sm btn-secondary" onclick="window.viewResult('${result.id}')">🔍 상세 보기</button>`;
    
    // 상세 보기 클릭 이벤트 속성 추가 (테이블 줄바꿈도 계속 지원)
    tr.style.cursor = 'pointer';
    tr.onclick = (e) => {
        // 만약 버튼 자체를 누른게 아니라면 바로보기 실행
        if (e.target.tagName !== 'BUTTON') window.viewResult(result.id);
    };
    tr.title = "클릭하여 자세한 결과를 확인하세요";
    
    // 내부 result 저장
    if(!window._compareResults) window._compareResults = {};
    if(result.id) window._compareResults[result.id] = result;
    
  } catch (err) {
    tr.children[2].innerHTML = `<span style="color:var(--danger)">❌ 오류 발생</span>`;
    tr.children[3].textContent = err.message;
  }
}


window.viewResult = async (id) => {
  try {
    let result = window._compareResults && window._compareResults[id];
    if (!result) {
        const r = await api(`/api/compare/results/${id}`);
        result = { ...r.detail, hostname: r.hostname, template_name: r.template_name };
    }
    renderResult(result);
  } catch (err) {
    toast(`결과 조회 실패: ${err.message}`, 'error');
  }
};

export function renderResult(result, containerId = 'compare-result-area') {
  const area = document.getElementById(containerId);
  if (!area) return;

  const isModal = containerId.includes('modal');
  const stickyTop = isModal ? '0' : '56px';

  const overall = result.overall;
  const statusIcons = { pass: '✅', review: '⚠️', fail: '❌' };

  // 1. 섹션별 그룹핑
  const grouped = {};
  result.items.forEach(item => {
      let sec = item.section || '기타 설정';
      
      // 골든 탭의 그룹핑 규칙과 어느정도 호환되도록 정리
      if (sec.startsWith('interface')) {
          if (item.id.includes('.uplink.') || item.id.includes('.L2.')) {
             // 이미 'interface (uplink)' 형태임
          } else {
             sec = 'INTERFACE (GENIE)';
          }
      }
      
      if (!grouped[sec]) grouped[sec] = [];
      grouped[sec].push(item);
  });

  // 2. HTML 생성
  const sectionHtmls = Object.keys(grouped).sort().map(sec => {
      const items = grouped[sec];
      const isUplink = sec.startsWith('interface (uplink)') || sec.includes('GigabitEthernet') || sec.includes('TenGigabit');
      const isL2 = sec.includes('(L2)');
      const sectionIcon = isUplink ? '🔗' : isL2 ? '🔀' : '📂';
      
      const itemsHtml = items.map(item => {
          let cleanLabel = item.label;
          // 인터페이스 섹션인 경우 '명칭 → ' 패턴 제거 (소급 적용)
          if (sec.toLowerCase().includes('interface') && cleanLabel.includes(' → ')) {
              cleanLabel = cleanLabel.split(' → ').pop();
          }

          return `
            <div class="result-item ${item.status}">
              <span class="result-item-icon">${statusIcons[item.status] || '?'}</span>
              <div>
                <div class="result-item-label">${cleanLabel}</div>
                ${item.status !== 'pass'
                  ? `<div class="result-item-msg">기대: <code>${item.expected}</code> / 실제: <code>${item.actual}</code> — ${item.message}</div>`
                  : ''}
              </div>
              <span class="result-item-status ${item.status}">${item.status.toUpperCase()}</span>
            </div>
          `;
      }).join('');

      return `
        <div class="section-group" style="margin-bottom: 24px;">
            <div class="section-group-header" style="background:var(--bg-secondary); padding:8px 12px; margin-bottom:8px; border-radius:6px; font-weight:bold; color:var(--accent); font-size:13px; display:flex; align-items:center; gap:8px; border-left: 3px solid var(--accent); position: sticky; top: ${stickyTop}; z-index: 5;">
                <span style="font-size:16px;">${sectionIcon}</span> 
                <span>${sec.toUpperCase()} <span style="color:var(--text-muted); font-size:11px; font-weight:normal;">(${items.length}개 항목)</span></span>
            </div>
            <div class="result-items" style="display: flex; flex-direction: column; gap: 6px;">
                ${itemsHtml}
            </div>
        </div>
      `;
  }).join('');

  area.innerHTML = `
    <div class="result-header" style="background: var(--bg-card); border-color: var(--border); margin-bottom: 24px;">
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
    <div class="results-container">
        ${sectionHtmls}
    </div>
  `;
  area.style.display = 'block';
  
  if (containerId === 'compare-result-area') {
      area.scrollIntoView({ behavior: 'smooth' });
  } else {
      area.scrollTop = 0;
  }
}
