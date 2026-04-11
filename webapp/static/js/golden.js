// golden.js — 골든 컨피그 탭

import { api, uploadFile, initDropZone, setLoading, toast } from './app.js';

let parsedData = null;   // 서버에서 받은 파싱 결과
let allItems = [];       // flatten_for_ui 결과
let conditionalRules = []; // [{ hostname_regex, items: [{id, section, label, value, match_type, weight}] }]
let filterSection = '';  // 현재 필터 섹션

export function initGolden() {
  const zone    = document.getElementById('golden-drop-zone');
  const input   = document.getElementById('golden-file-input');
  const saveBtn = document.getElementById('golden-save-btn');
  const selAll  = document.getElementById('golden-select-all');
  const selNone = document.getElementById('golden-select-none');
  const addRuleBtn = document.getElementById('golden-add-rule-btn');

  initDropZone(zone, input, files => handleGoldenUpload(files[0]));

  saveBtn.addEventListener('click', saveTemplate);
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

  list.innerHTML = filtered.map((item, idx) => {
    const realIdx = allItems.indexOf(item);
    return `
      <div class="item-row ${item.selected ? 'selected' : ''}" data-idx="${realIdx}">
        <input type="checkbox" class="item-check" ${item.selected ? 'checked' : ''} data-idx="${realIdx}">
        <span class="item-source ${item.source}">${item.source}</span>
        <span class="item-label" title="${item.label}">${item.label}</span>
        <span class="item-value" title="${item.value}">${item.value}</span>
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
    `;
  }).join('');

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

async function saveTemplate() {
  if (!parsedData) return toast('먼저 설정 파일을 업로드하세요.', 'error');

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
      }),
    });
    toast(`골든 템플릿 "${name}" 저장 완료`, 'success');
    
    // 상태 초기화
    document.getElementById('golden-template-name').value = '';
    document.getElementById('golden-hostname-regex').value = '';
    document.getElementById('golden-description').value = '';
    conditionalRules = [];
    document.getElementById('golden-conditional-container').innerHTML = '';
  } catch (err) {
    toast(`저장 실패: ${err.message}`, 'error');
  } finally {
    setLoading(btn, false);
  }
}
