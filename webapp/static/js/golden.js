// golden.js — 골든 컨피그 탭

import { api, uploadFile, initDropZone, setLoading, toast } from './app.js';

let parsedData = null;   // 서버에서 받은 파싱 결과
let allItems = [];       // flatten_for_ui 결과
let conditionalRules = []; // [{ hostname_regex, items: [{id, section, label, value, match_type, weight}] }]
let filterSection = '';  // 현재 필터 섹션
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
      match_type: item.source === 'genie' ? 'exact' : 'contains',
      weight: 'required',
      expected_value: item.value,
    }));

    document.getElementById('golden-hostname').textContent = data.hostname || '(알 수 없음)';
    document.getElementById('golden-section-count').textContent = data.section_count;
    document.getElementById('golden-item-count').textContent = allItems.length;
    document.getElementById('golden-results-area').style.display = 'block';

    buildSectionFilters();
    renderItems();

    zone.innerHTML = `
      <div class="drop-icon">✅</div>
      <h3>${file.name}</h3>
      <p>분석 완료 — 다른 파일을 올리려면 클릭</p>
    `;
  } catch (err) {
    zone.innerHTML = `
      <div class="drop-icon">📁</div>
      <h3>설정 파일을 드래그하거나 클릭하여 업로드</h3>
      <p>Cisco IOS / IOS-XE .cfg 파일 지원</p>
    `;
    toast(`업로드 실패: ${err.message}`, 'error');
  }
}

function buildSectionFilters() {
  const sections = [...new Set(allItems.map(i => i.section))].sort();
  const container = document.getElementById('golden-section-filters');
  container.innerHTML = `<button class="filter-btn active" data-section="">전체 (${allItems.length})</button>`;
  sections.forEach(s => {
    const count = allItems.filter(i => i.section === s).length;
    const btn = document.createElement('button');
    btn.className = 'filter-btn';
    btn.dataset.section = s;
    btn.textContent = `${s} (${count})`;
    container.appendChild(btn);
  });
}

function renderItems() {
  const list = document.getElementById('golden-items-list');
  const filtered = filterSection
    ? allItems.filter(i => i.section === filterSection)
    : allItems;

  // 섹션별 그룹핑 개선
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
      const firstLine = (item.label || '').trim();
      const firstWord = firstLine.split(' ')[0].toLowerCase();
      
      // Global config commands that should group together
      if (['aaa', 'vtp', 'snmp-server', 'logging', 'spanning-tree', 'ntp', 'crypto', 'boot'].includes(firstWord)) {
        sec = firstWord.toUpperCase();
      } else if (item.parent_header) {
        sec = item.parent_header;
      } else {
        if (firstLine.startsWith('interface ')) {
          sec = firstLine;
        }
      }
    }

    if (!grouped[sec]) grouped[sec] = [];
    grouped[sec].push(item);
  });

  const htmlParts = [];
  
  Object.keys(grouped).sort().forEach(sec => {
    htmlParts.push(`
      <div class="section-group-header" style="background:var(--bg-secondary); padding:8px 12px; margin-top:12px; margin-bottom:4px; border-radius:6px; font-weight:bold; color:var(--accent); font-size:13px; display:flex; align-items:center; gap:8px; border-left: 3px solid var(--accent);">
        <span style="font-size:16px;">📂</span> ${sec.toUpperCase()} <span style="color:var(--text-muted); font-size:11px; font-weight:normal;">(${grouped[sec].length}개 항목)</span>
      </div>
    `);
    
    grouped[sec].forEach(item => {
      const realIdx = allItems.indexOf(item);
      
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

      htmlParts.push(`
        <div class="item-row ${item.selected ? 'selected' : ''}" data-idx="${realIdx}" style="margin-left:14px;">
          <input type="checkbox" class="item-check" ${item.selected ? 'checked' : ''} data-idx="${realIdx}">
          <span class="item-source ${item.source}">${item.source}</span>
          <span class="item-label" title="${item.label}">${displayLabel}</span>
          <input type="text" class="item-expected-value" data-idx="${realIdx}" 
                 value="${(item.expected_value !== undefined ? item.expected_value : (item.value || '')).toString().replace(/"/g, '&quot;')}" 
                 title="원본: ${item.value}"
                 style="flex:1; max-width:180px; font-family:'Fira Code', monospace; font-size:11px; background:var(--bg-primary); color:var(--text-primary); border:1px solid var(--border); border-radius:4px; padding:2px 6px;">
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

  // 체크박스 이벤트
  list.querySelectorAll('.item-check').forEach(cb => {
    cb.addEventListener('change', () => {
      const idx = +cb.dataset.idx;
      allItems[idx].selected = cb.checked;
      cb.closest('.item-row').classList.toggle('selected', cb.checked);
    });
  });

  // match_type 변경
  list.querySelectorAll('.item-match-type').forEach(sel => {
    sel.addEventListener('change', () => {
      allItems[+sel.dataset.idx].match_type = sel.value;
    });
  });

  // weight 토글
  list.querySelectorAll('.item-weight').forEach(btn => {
    btn.addEventListener('click', () => {
      const idx = +btn.dataset.idx;
      allItems[idx].weight = allItems[idx].weight === 'required' ? 'optional' : 'required';
      btn.className = `item-weight ${allItems[idx].weight}`;
      btn.textContent = allItems[idx].weight;
    });
  });

  // expected value 텍스트박스 입력 감지
  list.querySelectorAll('.item-expected-value').forEach(ipt => {
    ipt.addEventListener('input', () => {
      const idx = +ipt.dataset.idx;
      allItems[idx].expected_value = ipt.value;
    });
  });
}

function toggleAll(checked) {
  const filtered = filterSection
    ? allItems.filter(i => i.section === filterSection)
    : allItems;
  filtered.forEach(i => i.selected = checked);
  renderItems();
}

function addConditionalRule() {
  const rule = {
    id: Date.now(),
    hostname_regex: '',
    items: [] // 템플릿의 현재 선택된 항목들을 복사해서 조건부로 쓸 수도 있음
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
        // Use all saved golden items as all items.
        // It's possible some UI items weren't saved, but for editing existing items it is sufficient.
        allItems = tpl.golden_items;
        filterSection = '';
        
        document.getElementById('golden-section-count').textContent = '?';
        document.getElementById('golden-item-count').textContent = allItems.length;
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
  if (!parsedData && !allItems.length) return toast('먼저 설정 파일을 업로드하세요.', 'error');

  const name = document.getElementById('golden-template-name').value.trim();
  const regex = document.getElementById('golden-hostname-regex').value.trim();
  const desc = document.getElementById('golden-description').value.trim();

  if (!name) return toast('템플릿 이름을 입력하세요.', 'error');

  const selectedItems = allItems.filter(i => i.selected);
  if (selectedItems.length === 0) return toast('최소 1개 항목을 선택하세요.', 'error');

  const btn = document.getElementById('golden-save-btn');
  setLoading(btn, true, '저장 중...');

  const osType = document.getElementById('golden-os-select').value;

  try {
    const res = await api('/api/golden/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name, 
        hostname_regex: regex, 
        description: desc,
        os_type: osType,
        selected_items: selectedItems,
        conditional_rules: conditionalRules,
        golden_parsed: parsedData.parsed,
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
    
    // 탭 목록 갱신 트리거
    if (window.loadGoldenTemplates) {
        window.loadGoldenTemplates();
    }
  } catch (err) {
    toast(`저장 실패: ${err.message}`, 'error');
  } finally {
    setLoading(btn, false);
  }
}
