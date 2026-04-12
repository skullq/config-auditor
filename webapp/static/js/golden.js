// golden.js — 골든 컨피그 탭

import { api, uploadFile, initDropZone, setLoading, toast } from './app.js';

let parsedData = null;   // 서버에서 받은 파싱 결과 (인터페이스 제외)
let allItems = [];       // 일반 설정 항목 (flatten_for_ui, 인터페이스 제외)
let intfItems = [];      // 인터페이스 전용 항목 (업링크 + L2)
let conditionalRules = [];
let filterSection = '';
let currentEditingId = null;

export function initGolden() {
  const zone    = document.getElementById('golden-drop-zone');
  const input   = document.getElementById('golden-file-input');
  const saveBtn = document.getElementById('golden-save-btn');
  const cancelBtn = document.getElementById('golden-cancel-btn');
  const selAll  = document.getElementById('golden-select-all');
  const selNone = document.getElementById('golden-select-none');
  const addRuleBtn = document.getElementById('golden-add-rule-btn');

  initDropZone(zone, input, files => handleGoldenUpload(files[0]));

  // 인터페이스 전용 드롭존
  const intfZone  = document.getElementById('golden-intf-drop-zone');
  const intfInput = document.getElementById('golden-intf-file-input');
  if (intfZone && intfInput) {
    initDropZone(intfZone, intfInput, files => handleIntfUpload(files[0]));
  }

  saveBtn.addEventListener('click', saveTemplate);
  cancelBtn.addEventListener('click', () => {
    currentEditingId = null;
    cancelBtn.style.display = 'none';
    document.getElementById('golden-template-name').value = '';
    document.getElementById('golden-hostname-regex').value = '';
    document.getElementById('golden-description').value = '';
    toast('수정이 취소되었습니다.', 'info');
  });
  selAll.addEventListener('click',  () => toggleAll(true));
  selNone.addEventListener('click', () => toggleAll(false));
  addRuleBtn.addEventListener('click', addConditionalRule);

  // 필터 버튼 클릭
  document.getElementById('golden-section-filters').addEventListener('click', e => {
    const btn = e.target.closest('.filter-btn');
    if (!btn) return;
    document.querySelectorAll('#golden-section-filters .filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    filterSection = btn.dataset.section || '';
    renderItems();
  });
}

// ── 일반 골든 설정 업로드 (인터페이스 제외) ──────────────────────────

async function handleGoldenUpload(file) {
  const zone = document.getElementById('golden-drop-zone');
  const osType = document.getElementById('golden-os-select').value;
  zone.innerHTML = `<div class="loading-overlay"><div class="spinner"></div><span>Genie로 분석 중... (${osType})</span></div>`;

  try {
    const data = await uploadFile(`/api/golden/upload?os=${osType}`, file);
    if (data.os) document.getElementById('golden-os-select').value = data.os;
    parsedData = data;
    allItems = data.items.map(item => ({
      ...item,
      selected: true,
      match_type: item.match_type || (item.source === 'genie' ? 'exact' : 'contains'),
      weight: item.weight || 'required',
      expected_value: item.value,
    }));

    document.getElementById('golden-hostname').textContent = data.hostname || '(알 수 없음)';
    document.getElementById('golden-section-count').textContent = data.section_count;
    document.getElementById('golden-item-count').textContent = allItems.length + intfItems.length;
    document.getElementById('golden-results-area').style.display = 'block';

    buildSectionFilters();
    renderItems();

    zone.innerHTML = `
      <div class="drop-icon">✅</div>
      <h3>${file.name}</h3>
      <p>분석 완료 (인터페이스 섹션 제외) — 다른 파일을 올리려면 클릭</p>
    `;
  } catch (err) {
    zone.innerHTML = `
      <div class="drop-icon">📁</div>
      <h3>설정 파일을 드래그하거나 클릭하여 업로드</h3>
      <p>Cisco IOS / IOS-XE 설정 파일 (.cfg, .txt, .conf)</p>
    `;
    toast(`업로드 실패: ${err.message}`, 'error');
  }
}

// ── 인터페이스 전용 업로드 ───────────────────────────────────────────

async function handleIntfUpload(file) {
  const zone = document.getElementById('golden-intf-drop-zone');
  zone.innerHTML = `<div class="loading-overlay"><div class="spinner"></div><span>인터페이스 분석 중...</span></div>`;
  try {
    const data = await uploadFile('/api/golden/upload-interface', file);
    intfItems = data.items.map(item => ({
      ...item,
      selected: true,
      expected_value: item.value,
    }));

    document.getElementById('intf-total-count').textContent = data.total;
    document.getElementById('intf-uplink-count').textContent = data.uplink_count;
    document.getElementById('intf-l2-count').textContent = data.l2_count;
    document.getElementById('golden-intf-summary').style.display = 'block';
    document.getElementById('golden-item-count').textContent = allItems.length + intfItems.length;
    document.getElementById('golden-results-area').style.display = 'block';

    buildSectionFilters();
    renderItems();

    zone.innerHTML = `
      <div class="drop-icon">✅</div>
      <h3>${file.name}</h3>
      <p>인터페이스 분석 완료: 업링크 ${data.uplink_count}개 / L2 ${data.l2_count}개 — 클릭하여 재업로드</p>
    `;
    toast(`인터페이스 분석 완료: 총 ${data.total}개 (업링크 ${data.uplink_count} / L2 ${data.l2_count})`, 'success');
  } catch (err) {
    zone.innerHTML = `
      <div class="drop-icon">🔌</div>
      <h3>인터페이스 설정 파일을 드래그하거나 클릭하여 업로드</h3>
      <p>동일 파일 또는 별도의 인터페이스 설정 파일 가능</p>
    `;
    toast(`인터페이스 업로드 실패: ${err.message}`, 'error');
  }
}

// ── 섹션 필터 빌드 ──────────────────────────────────────────────────

function buildSectionFilters() {
  const combined = [...allItems, ...intfItems];
  const sections = [...new Set(combined.map(i => i.section))].sort();
  const container = document.getElementById('golden-section-filters');
  container.innerHTML = `<button class="filter-btn active" data-section="">전체 (${combined.length})</button>`;
  sections.forEach(s => {
    const count = combined.filter(i => i.section === s).length;
    const btn = document.createElement('button');
    btn.className = 'filter-btn';
    btn.dataset.section = s;
    btn.textContent = `${s} (${count})`;
    container.appendChild(btn);
  });
}

// ── 항목 렌더링 ─────────────────────────────────────────────────────

function renderItems() {
  const list = document.getElementById('golden-items-list');
  const combined = [...allItems, ...intfItems];
  const filtered = filterSection
    ? combined.filter(i => i.section === filterSection)
    : combined;

  // 섹션별 그룹핑
  const grouped = {};
  filtered.forEach(item => {
    let sec = item.section || '기타';

    if (item.source === 'genie') {
      const parts = item.id.split('.');
      if (parts[0] === 'interface') {
        if (parts.length > 2 && parts[1] === 'interfaces') {
          sec = `interface ${parts[2]}`;
        } else if (parts.length > 1 && parts[1] !== 'raw') {
          sec = `interface ${parts[1]}`;
        }
      }
    } else if (item.source === 'raw') {
      // 인터페이스 항목은 section이 이미 'interface (uplink)' or 'interface (L2)' 로 설정됨
      if (sec.startsWith('interface (')) {
        // 업링크는 parent_header 기준으로 세부 그룹
        if (item.intf_type === 'uplink' && item.parent_header) {
          sec = item.parent_header;
        }
        // L2는 섹션명 유지
      } else {
        const firstLine = (item.label || '').trim();
        const firstWord = firstLine.split(' ')[0].toLowerCase();
        if (['aaa', 'vtp', 'snmp-server', 'logging', 'spanning-tree', 'ntp', 'crypto', 'boot', 'feature'].includes(firstWord)) {
          sec = firstWord.toUpperCase();
        } else if (item.parent_header) {
          sec = item.parent_header;
        }
      }
    }

    if (!grouped[sec]) grouped[sec] = [];
    grouped[sec].push(item);
  });

  const htmlParts = [];

  Object.keys(grouped).sort().forEach(sec => {
    const isUplink = sec.startsWith('interface ') && !sec.startsWith('interface (L2');
    const isL2 = sec.startsWith('interface (L2');
    const sectionIcon = isUplink ? '🔗' : isL2 ? '🔀' : '📂';
    const sectionHint = isUplink ? ' [업링크 — 번호+옵션 검증]' : isL2 ? ' [L2 — 옵션 기준 검증]' : '';

    htmlParts.push(`
      <div class="section-group-header" style="background:var(--bg-secondary); padding:8px 12px; margin-top:12px; margin-bottom:4px; border-radius:6px; font-weight:bold; color:var(--accent); font-size:13px; display:flex; align-items:center; gap:8px; border-left: 3px solid var(--accent);">
        <span style="font-size:16px;">${sectionIcon}</span> ${sec.toUpperCase()}${sectionHint} <span style="color:var(--text-muted); font-size:11px; font-weight:normal;">(${grouped[sec].length}개 항목)</span>
      </div>
    `);

    grouped[sec].forEach(item => {
      const realIdx = combined.indexOf(item);

      let displayLabel = item.label;
      if (item.source === 'genie') {
        const parts = item.id.split('.');
        if (parts[0] === 'interface') {
          const offset = parts[1] === 'interfaces' ? 3 : 2;
          if (parts.length > offset) {
            displayLabel = parts.slice(offset).join(' ').replace(/_/g, ' ');
          }
        } else {
          displayLabel = parts.slice(1).join(' ').replace(/_/g, ' ');
        }
      }

      // 업링크 IP 옵션은 시각적으로 약하게 표시
      const isIpOpt = item.intf_type === 'uplink' && item.match_type === 'exists';
      
      const valText = (item.expected_value !== undefined ? item.expected_value : (item.value || '')).toString();
      const isMultiline = valText.includes('\n') || item.section === 'banner';

      htmlParts.push(`
        <div class="item-row ${item.selected ? 'selected' : ''} ${isMultiline ? 'multiline' : ''}" data-idx="${realIdx}" style="margin-left:14px;${isIpOpt ? 'opacity:0.65;' : ''}">
          <input type="checkbox" class="item-check" ${item.selected ? 'checked' : ''} data-idx="${realIdx}">
          <span class="item-source ${item.source}">${item.intf_type ? item.intf_type : item.source}</span>
          <span class="item-label" title="${item.label}">${displayLabel}</span>
          
          ${isMultiline ? `
            <textarea class="item-expected-value" data-idx="${realIdx}" 
                      style="flex:1; max-width:350px; min-height:60px; font-family:'Fira Code', monospace; font-size:11px; background:var(--bg-primary); color:var(--text-primary); border:1px solid var(--border); border-radius:4px; padding:4px 6px; resize:vertical;"
                      placeholder="기대값 입력...">${valText.replace(/"/g, '&quot;')}</textarea>
          ` : `
            <input type="text" class="item-expected-value" data-idx="${realIdx}" 
                   value="${valText.replace(/"/g, '&quot;')}" 
                   title="원본: ${item.value}"
                   style="flex:1; max-width:180px; font-family:'Fira Code', monospace; font-size:11px; background:var(--bg-primary); color:var(--text-primary); border:1px solid var(--border); border-radius:4px; padding:2px 6px;">
          `}
          
          <div class="item-controls">
            <select class="item-match-type" data-idx="${realIdx}">
              <option value="exists"   ${item.match_type==='exists'   ? 'selected':''}>exists</option>
              <option value="exact"    ${item.match_type==='exact'    ? 'selected':''}>exact</option>
              <option value="contains" ${item.match_type==='contains' ? 'selected':''}>contains</option>
              <option value="regex"    ${item.match_type==='regex'    ? 'selected':''}>regex</option>
            </select>
            <button class="item-weight ${item.weight}" data-idx="${realIdx}">${item.weight}</button>
          </div>
        </div>
      `);
    });
  });

  list.innerHTML = htmlParts.join('');

  // 이벤트 바인딩 — combined 배열 기준 idx 사용
  list.querySelectorAll('.item-check').forEach(cb => {
    cb.addEventListener('change', () => {
      const idx = +cb.dataset.idx;
      combined[idx].selected = cb.checked;
      cb.closest('.item-row').classList.toggle('selected', cb.checked);
    });
  });

  list.querySelectorAll('.item-match-type').forEach(sel => {
    sel.addEventListener('change', () => {
      combined[+sel.dataset.idx].match_type = sel.value;
    });
  });

  list.querySelectorAll('.item-weight').forEach(btn => {
    btn.addEventListener('click', () => {
      const idx = +btn.dataset.idx;
      combined[idx].weight = combined[idx].weight === 'required' ? 'optional' : 'required';
      btn.className = `item-weight ${combined[idx].weight}`;
      btn.textContent = combined[idx].weight;
    });
  });

  list.querySelectorAll('.item-expected-value').forEach(ipt => {
    ipt.addEventListener('input', () => {
      combined[+ipt.dataset.idx].expected_value = ipt.value;
    });
  });
}

function toggleAll(checked) {
  const combined = [...allItems, ...intfItems];
  const filtered = filterSection
    ? combined.filter(i => i.section === filterSection)
    : combined;
  filtered.forEach(i => i.selected = checked);
  renderItems();
}

function addConditionalRule() {
  const rule = {
    id: Date.now(),
    hostname_regex: '',
    items: []
  };
  conditionalRules.push(rule);
  renderRules();
}

function renderRules() {
  const container = document.getElementById('golden-conditional-container');
  container.innerHTML = conditionalRules.map((rule, idx) => `
    <div class="card" style="border-style: dashed; border-color: var(--accent); margin-bottom: 12px; padding: 16px;">
      <div class="flex justify-between items-center mb-2">
        <strong>교집합 규칙 #${idx + 1}</strong>
        <button class="btn btn-sm btn-danger" onclick="window.removeRule(${idx})">삭제</button>
      </div>
      <div class="form-group">
        <label class="form-label">호스트명 일치 시 적용 (Regex)</label>
        <input type="text" class="form-input" placeholder="예: ^NY-.*-AGG" 
               value="${rule.hostname_regex}" 
               onchange="window.updateRuleRegex(${idx}, this.value)">
      </div>
      <p class="text-muted" style="font-size:11px">※ 이 호스트명 패턴과 일치하면, 메인 리스트에서 선택된 항목 외에 추가적인 검증이 수행됩니다.</p>
    </div>
  `).join('');
}

window.removeRule = idx => {
  conditionalRules.splice(idx, 1);
  renderRules();
};

window.updateRuleRegex = (idx, val) => {
  conditionalRules[idx].hostname_regex = val;
};

window.editTemplate = async (id) => {
    try {
        const res = await fetch(`/api/golden/templates/${id}`);
        if (!res.ok) throw new Error('템플릿을 불러오지 못했습니다.');
        const tpl = await res.json();

        currentEditingId = tpl.id;
        document.getElementById('golden-template-name').value = tpl.name;
        document.getElementById('golden-hostname-regex').value = tpl.hostname_regex || '';
        document.getElementById('golden-description').value = tpl.description || '';
        document.getElementById('golden-os-select').value = tpl.os || 'iosxe';

        conditionalRules = tpl.conditional_rules || [];
        renderRules();

        parsedData = { parsed: tpl.golden_parsed, hostname: 'from template', items: [] };
        // 저장된 항목을 인터페이스/일반으로 분리
        allItems = tpl.golden_items.filter(i => !i.section?.startsWith('interface ('));
        intfItems = tpl.golden_items.filter(i => i.section?.startsWith('interface ('));
        filterSection = '';

        document.getElementById('golden-section-count').textContent = '?';
        document.getElementById('golden-item-count').textContent = allItems.length + intfItems.length;
        document.getElementById('golden-results-area').style.display = 'block';
        document.getElementById('golden-cancel-btn').style.display = 'inline-block';

        buildSectionFilters();
        renderItems();
        toast('템플릿을 수정합니다.', 'info');
        window.scrollTo(0, 0);
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function saveTemplate() {
  const combined = [...allItems, ...intfItems];
  if (!parsedData && combined.length === 0) return toast('먼저 설정 파일을 업로드하세요.', 'error');

  const name = document.getElementById('golden-template-name').value.trim();
  const regex = document.getElementById('golden-hostname-regex').value.trim();
  const desc = document.getElementById('golden-description').value.trim();

  if (!name) return toast('템플릿 이름을 입력하세요.', 'error');

  const selectedItems = combined.filter(i => i.selected);
  if (selectedItems.length === 0) return toast('최소 1개 항목을 선택하세요.', 'error');

  const btn = document.getElementById('golden-save-btn');
  setLoading(btn, true, '저장 중...');

  const osType = document.getElementById('golden-os-select').value;

  try {
    await api('/api/golden/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name,
        hostname_regex: regex,
        description: desc,
        os_type: osType,
        selected_items: selectedItems,
        conditional_rules: conditionalRules,
        golden_parsed: parsedData?.parsed || {},
        template_id: currentEditingId,
      }),
    });
    toast(`골든 템플릿 "${name}" 저장 완료`, 'success');

    // 상태 초기화
    document.getElementById('golden-template-name').value = '';
    document.getElementById('golden-hostname-regex').value = '';
    document.getElementById('golden-description').value = '';
    conditionalRules = [];
    currentEditingId = null;
    document.getElementById('golden-cancel-btn').style.display = 'none';
    document.getElementById('golden-conditional-container').innerHTML = '';

    if (window.loadGoldenTemplates) {
      window.loadGoldenTemplates();
    }
  } catch (err) {
    toast(`저장 실패: ${err.message}`, 'error');
  } finally {
    setLoading(btn, false);
  }
}
