// golden.js — 골든 컨피그 탭 (cisco-config-parser 3.0.0 & Drag & Drop 블록 지원)

import { api, uploadFile, initDropZone, setLoading, toast } from './app.js';

let parsedData = null;   // 서버에서 받은 파싱 결과
let parsedBlocks = [];   // cisco-config-parser로 추출된 전체 블록 목록 (Drag & Drop 대상)
let allItems = [];       // 일반 및 전체 설정 항목 (flatten_for_ui)
let intfItems = [];      // 하위 호환용 인터페이스 항목
let conditionalRules = [];
let filterBlock = '';    // 선택된 블록 ID (빈 문자열이면 전체)
let filterSection = '';
let currentEditingId = null;
let draggedBlockIndex = null;

function escapeHtml(s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

export function initGolden() {
  const zone    = document.getElementById('golden-drop-zone');
  const input   = document.getElementById('golden-file-input');
  const saveBtn = document.getElementById('golden-save-btn');
  const cancelBtn = document.getElementById('golden-cancel-btn');
  const selAll  = document.getElementById('golden-select-all');
  const selNone = document.getElementById('golden-select-none');
  const addRuleBtn = document.getElementById('golden-add-rule-btn');
  const expandBlocksBtn = document.getElementById('golden-blocks-expand-all');
  const collapseBlocksBtn = document.getElementById('golden-blocks-collapse-all');

  initDropZone(zone, input, files => handleUnifiedUpload(files[0]));

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

  // 실시간 프리뷰 복사 & 접기 버튼
  const copyPreviewBtn = document.getElementById('preview-copy-btn');
  const togglePreviewBtn = document.getElementById('preview-toggle-btn');
  const previewCodeContainer = document.getElementById('preview-code-container');

  if (copyPreviewBtn) {
    copyPreviewBtn.addEventListener('click', () => {
      const code = document.getElementById('golden-live-preview-code')?.textContent || '';
      navigator.clipboard.writeText(code).then(() => {
        toast('최종 템플릿 설정이 클립보드에 복사되었습니다.', 'success');
      }).catch(() => {
        toast('클립보드 복사 실패', 'error');
      });
    });
  }

  if (togglePreviewBtn && previewCodeContainer) {
    togglePreviewBtn.addEventListener('click', () => {
      previewCodeContainer.classList.toggle('collapsed');
      togglePreviewBtn.textContent = previewCodeContainer.classList.contains('collapsed') ? '⊞ 펼치기' : '⊟ 접기';
    });
  }

  if (expandBlocksBtn) {
    expandBlocksBtn.addEventListener('click', () => {
      parsedBlocks.forEach(b => b.expanded = true);
      renderBlocks();
    });
  }

  if (collapseBlocksBtn) {
    collapseBlocksBtn.addEventListener('click', () => {
      parsedBlocks.forEach(b => b.expanded = false);
      renderBlocks();
    });
  }

  // 섹션/블록 필터 버튼 클릭
  document.getElementById('golden-section-filters').addEventListener('click', e => {
    const btn = e.target.closest('.filter-btn');
    if (!btn) return;
    document.querySelectorAll('#golden-section-filters .filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    filterBlock = btn.dataset.block !== undefined ? btn.dataset.block : '';
    filterSection = btn.dataset.section || '';
    renderBlocks();
    renderItems();
  });
}

// ── 통합 골든 설정 업로드 (cisco-config-parser + 인터페이스) ────────

async function handleUnifiedUpload(file) {
  const zone = document.getElementById('golden-drop-zone');
  const osType = document.getElementById('golden-os-select').value;
  
  const hasExisting = allItems.length > 0 || intfItems.length > 0;
  let isMerge = false;
  
  if (hasExisting) {
    isMerge = confirm('기존 로드된 설정이 있습니다.\n확인: 현재 설정에 병합 (중복 시 새 데이터로 업데이트)\n취소: 기존 설정을 삭제하고 새로 시작');
  }

  zone.innerHTML = `<div class="loading-overlay"><div class="spinner"></div><span>설정 분석 중... (${osType})</span></div>`;

  try {
    const data = await uploadFile(`/api/golden/upload?os=${osType}`, file);
    if (data.os) document.getElementById('golden-os-select').value = data.os;
    
    // 블록 데이터 로드
    parsedBlocks = (data.blocks || []).map((b, idx) => ({
      ...b,
      order: idx + 1,
      enabled: true,
      expanded: false
    }));

    // 1. 일반 설정 병합
    const newGeneral = data.general_items.map(item => ({
      ...item,
      selected: true,
      match_type: item.match_type || (item.source === 'cisco_config_parser' || item.source === 'genie' ? 'exact' : 'contains'),
      weight: item.weight || 'required',
      expected_value: item.value,
    }));

    if (isMerge) {
      const existingIds = new Set(newGeneral.map(i => i.id));
      allItems = [...allItems.filter(i => !existingIds.has(i.id)), ...newGeneral];
    } else {
      allItems = newGeneral;
      parsedData = data.parsed;
    }

    // 2. 인터페이스 설정 병합
    const newIntf = data.intf_items.map(item => ({
      ...item,
      selected: true,
      expected_value: item.value,
    }));

    if (isMerge) {
      const existingIntfIds = new Set(newIntf.map(i => i.id));
      intfItems = [...intfItems.filter(i => !existingIntfIds.has(i.id)), ...newIntf];
    } else {
      intfItems = newIntf;
    }

    // 3. UI 업데이트
    document.getElementById('golden-hostname').textContent = data.hostname || '(알 수 없음)';
    document.getElementById('golden-section-count').textContent = data.section_count;
    document.getElementById('golden-item-count').textContent = allItems.length + intfItems.length;
    
    // 인터페이스 요약 업데이트
    document.getElementById('intf-total-count').textContent = data.intf_summary.total;
    document.getElementById('intf-uplink-count').textContent = data.intf_summary.uplink_count;
    document.getElementById('intf-l2-count').textContent = data.intf_summary.l2_count;
    document.getElementById('golden-intf-summary').style.display = 'block';
    
    // Drag & Drop 블록 카드 렌더링
    const blocksCard = document.getElementById('golden-blocks-card');
    if (parsedBlocks.length > 0) {
      blocksCard.style.display = 'block';
      renderBlocks();
    } else {
      blocksCard.style.display = 'none';
    }

    document.getElementById('golden-results-area').style.display = 'block';

    buildSectionFilters();
    renderItems();

    zone.innerHTML = `
      <div class="drop-icon">✅</div>
      <h3>${file.name}</h3>
      <p>설정 분석 완료 — 다른 파일을 올리려면 클릭</p>
    `;
    toast(isMerge ? '설정이 성공적으로 병합되었습니다.' : '설정 분석 완료', 'success');
  } catch (err) {
    zone.innerHTML = `
      <div class="drop-icon">📁+🔌</div>
      <h3>설정 파일을 드래그하거나 클릭하여 업로드</h3>
      <p>전체 설정 또는 인터페이스 설정 파일 (.cfg, .txt, .conf)</p>
    `;
    toast(`업로드 실패: ${err.message}`, 'error');
  }
}

// ── Drag & Drop 블록 렌더링 ──────────────────────────────────────────

function renderBlocks() {
  const container = document.getElementById('golden-blocks-list');
  if (!container) return;

  function escapeHtml(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function renderTree(treeNodes) {
    if (!treeNodes || treeNodes.length === 0) return '';
    return `
      <div class="tree-container">
        ${treeNodes.map(node => {
          if (node.children && node.children.length > 0) {
            return `
              <div class="tree-section-node">
                <div class="tree-section-header">
                  <span>📂</span>
                  <span>${escapeHtml(node.line)}</span>
                  <span class="badge text-xs" style="margin-left:auto">${node.children.length}개 설정</span>
                </div>
                <div class="tree-children-list">
                  ${node.children.map((c, cIdx) => {
                    const isLast = (cIdx === node.children.length - 1);
                    const branch = isLast ? '└──' : '├──';
                    return `
                      <div class="tree-child-item">
                        <span class="tree-branch-symbol">${branch}</span>
                        <span>${escapeHtml(c.line)}</span>
                      </div>
                    `;
                  }).join('')}
                </div>
              </div>
            `;
          } else {
            return `
              <div class="tree-leaf-item">
                <span>📄</span>
                <span>${escapeHtml(node.line)}</span>
              </div>
            `;
          }
        }).join('')}
      </div>
    `;
  }

  container.innerHTML = parsedBlocks.map((b, idx) => `
    <div class="block-card ${b.block_id === filterBlock ? 'active-selected' : ''}" draggable="true" data-index="${idx}" data-block-id="${b.block_id}">
      <div class="block-header" data-index="${idx}">
        <div class="block-drag-handle" title="끌어서 순서 변경">⋮⋮</div>
        <span class="block-order-badge">#${idx + 1}</span>
        <span class="block-title">${b.name}</span>
        <span class="block-count-badge">${b.item_count}개 항목</span>
        <input type="checkbox" class="block-toggle-check" data-idx="${idx}" ${b.enabled ? 'checked' : ''} title="블록 전체 선택/해제">
        <span class="block-chevron ${b.expanded ? 'expanded' : ''}" title="상세 트리 보기">▼</span>
      </div>
      <div class="block-body ${b.expanded ? 'expanded' : ''}">
        ${b.tree_nodes && b.tree_nodes.length > 0 ? renderTree(b.tree_nodes) : `
          <div class="block-items-inner">
            ${(b.items || []).map(item => `
              <div class="item-row ${item.selected !== false ? 'selected' : ''}" style="margin-bottom:4px; padding:6px 10px;">
                <span class="item-label">${escapeHtml(item.label)}</span>
                <span class="item-value" title="${escapeHtml(item.value)}">${escapeHtml(item.value)}</span>
              </div>
            `).join('')}
          </div>
        `}
      </div>
    </div>
  `).join('');

  // 1. 이벤트 바인딩: 헤더 클릭 (필터 선택 또는 트리 펼치기/접기)
  container.querySelectorAll('.block-header').forEach(header => {
    header.addEventListener('click', (e) => {
      if (e.target.closest('.block-toggle-check') || e.target.closest('.block-drag-handle')) {
        return;
      }
      const idx = +header.dataset.index;
      const block = parsedBlocks[idx];

      if (e.target.closest('.block-chevron')) {
        // 화살표 클릭 시에만 블록 내부 트리 펼치기/접기
        parsedBlocks[idx].expanded = !parsedBlocks[idx].expanded;
        renderBlocks();
        return;
      }

      // 블록 헤더 클릭 시 우측 상세 설정 필터링 토글
      filterBlock = (filterBlock === block.block_id) ? '' : block.block_id;
      
      // 필터 버튼 active 상태 동기화
      document.querySelectorAll('#golden-section-filters .filter-btn').forEach(btn => {
        if ((filterBlock === '' && btn.dataset.block === '') || (btn.dataset.block === filterBlock)) {
          btn.classList.add('active');
          btn.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
        } else {
          btn.classList.remove('active');
        }
      });

      renderBlocks();
      renderItems();
    });
  });

  // 2. 이벤트 바인딩: 블록 체크박스 (일괄 On/Off)
  container.querySelectorAll('.block-toggle-check').forEach(cb => {
    cb.addEventListener('change', (e) => {
      e.stopPropagation();
      const idx = +cb.dataset.idx;
      const block = parsedBlocks[idx];
      block.enabled = cb.checked;

      // 블록 내부 아이템들의 선택 상태 동기화
      const blockItemIds = new Set((block.items || []).map(i => i.id));
      allItems.forEach(i => {
        if (blockItemIds.has(i.id)) {
          i.selected = block.enabled;
        }
      });
      intfItems.forEach(i => {
        if (blockItemIds.has(i.id)) {
          i.selected = block.enabled;
        }
      });

      buildSectionFilters();
      renderItems();
      const selectedTotal = [...allItems, ...intfItems].filter(i => i.selected).length;
      document.getElementById('golden-item-count').textContent = selectedTotal;
      updateLivePreview();
    });
  });

  // 3. Drag & Drop 이벤트 바인딩
  const cards = container.querySelectorAll('.block-card');
  cards.forEach(card => {
    card.addEventListener('dragstart', (e) => {
      draggedBlockIndex = +card.dataset.index;
      card.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', draggedBlockIndex);
    });

    card.addEventListener('dragover', (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      card.classList.add('drag-over');
    });

    card.addEventListener('dragleave', () => {
      card.classList.remove('drag-over');
    });

    card.addEventListener('drop', (e) => {
      e.preventDefault();
      card.classList.remove('drag-over');
      const targetIndex = +card.dataset.index;
      if (draggedBlockIndex === null || draggedBlockIndex === targetIndex) return;

      // 배열 순서 재정렬
      const movedItem = parsedBlocks.splice(draggedBlockIndex, 1)[0];
      parsedBlocks.splice(targetIndex, 0, movedItem);

      // order 값 재부여
      parsedBlocks.forEach((b, i) => b.order = i + 1);

      // allItems 순서도 블록 순서에 맞춰 재정렬
      reorderItemsByBlocks();

      draggedBlockIndex = null;
      renderBlocks();
      renderItems();
      buildSectionFilters();
      updateLivePreview();
      toast('블록 감사 순서가 변경되었습니다.', 'info');
    });

    card.addEventListener('dragend', () => {
      card.classList.remove('dragging');
      cards.forEach(c => c.classList.remove('drag-over'));
      draggedBlockIndex = null;
    });
  });
}

function reorderItemsByBlocks() {
  const blockOrderMap = new Map();
  parsedBlocks.forEach((b, idx) => {
    (b.items || []).forEach(it => {
      blockOrderMap.set(it.id, idx);
    });
  });

  allItems.sort((a, b) => {
    const orderA = blockOrderMap.has(a.id) ? blockOrderMap.get(a.id) : 999;
    const orderB = blockOrderMap.has(b.id) ? blockOrderMap.get(b.id) : 999;
    return orderA - orderB;
  });
}

// ── 섹션 / 블록 필터 빌드 ──────────────────────────────────────────

function buildSectionFilters() {
  const container = document.getElementById('golden-section-filters');
  if (!container) return;

  if (parsedBlocks && parsedBlocks.length > 0) {
    const combined = [...allItems, ...intfItems];
    const totalCount = combined.length;
    let html = `<button class="filter-btn ${filterBlock === '' ? 'active' : ''}" data-block="">전체 (${totalCount})</button>`;
    
    parsedBlocks.forEach(b => {
      const count = (b.items || []).length;
      const isActive = (filterBlock === b.block_id) ? 'active' : '';
      const isDisabled = !b.enabled ? 'disabled-block' : '';
      html += `<button class="filter-btn ${isActive} ${isDisabled}" data-block="${b.block_id}">${escapeHtml(b.name)} (${count})</button>`;
    });
    container.innerHTML = html;
  } else {
    const combined = [...allItems, ...intfItems];
    const sections = [...new Set(combined.map(i => i.section))].sort();
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
}

// ── 상세 항목 렌더링 ────────────────────────────────────────────────

function renderItems() {
  const list = document.getElementById('golden-items-list');
  const combined = [...allItems, ...intfItems];

  const labelEl = document.getElementById('golden-current-filter-label');
  if (labelEl) {
    if (filterBlock) {
      const activeBlock = parsedBlocks.find(b => b.block_id === filterBlock);
      labelEl.textContent = activeBlock ? `[${activeBlock.name}] 필터링 됨` : '필터링 됨';
      labelEl.style.color = 'var(--accent)';
    } else {
      labelEl.textContent = `전체 (${combined.length}개 항목)`;
      labelEl.style.color = 'var(--text-secondary)';
    }
  }

  if (parsedBlocks && parsedBlocks.length > 0) {
    const targetBlocks = filterBlock ? parsedBlocks.filter(b => b.block_id === filterBlock) : parsedBlocks;
    const htmlParts = [];

    targetBlocks.forEach((block, bIdx) => {
      const blockItemIds = new Set((block.items || []).map(i => i.id));
      const blockItems = combined.filter(i => blockItemIds.has(i.id));
      if (blockItems.length === 0) return;

      const selectedCount = blockItems.filter(i => i.selected).length;

      htmlParts.push(`
        <div class="section-group-header flex justify-between items-center" style="background:var(--bg-secondary); padding:8px 12px; margin-top:16px; border-radius:4px; border-left:4px solid var(--accent);">
          <div>
            <span class="block-order-badge" style="margin-right:6px">#${block.order || (bIdx + 1)}</span>
            <strong>${escapeHtml(block.name)}</strong>
            <span class="text-muted" style="font-size:11px">(${selectedCount}/${blockItems.length}개 선택됨)</span>
          </div>
          <div class="flex gap-2">
            <button class="btn btn-secondary btn-sm block-item-toggle" data-block-id="${block.block_id}" data-val="true" style="padding:2px 8px; font-size:11px">전체 선택</button>
            <button class="btn btn-secondary btn-sm block-item-toggle" data-block-id="${block.block_id}" data-val="false" style="padding:2px 8px; font-size:11px">전체 해제</button>
          </div>
        </div>
      `);

      blockItems.forEach(item => {
        const realIdx = combined.indexOf(item);
        const isBanner = (item.section || '').toLowerCase() === 'banner';
        const isExists = item.match_type === 'exists';
        const valText = item.expected_value !== undefined ? item.expected_value : item.value;
        const displayVal = isExists ? '(임의의 값 허용 - 존재 여부 확인)' : valText;
        const placeholderText = item.match_type === 'contains' 
          ? '예: *CE1* 또는 키워드' 
          : item.match_type === 'regex' 
          ? '예: ^CE_ (정규표현식)' 
          : item.match_type === 'exists' 
          ? '존재 여부만 검사 (어떤 값이든 허용)' 
          : '정확한 기대값 입력 (예: 17.12)';

        htmlParts.push(`
          <div class="item-row ${item.selected ? 'selected' : ''}" data-idx="${realIdx}">
            <input type="checkbox" class="item-check" data-idx="${realIdx}" ${item.selected ? 'checked' : ''}>
            <span class="item-label" title="${escapeHtml(item.label)}">${escapeHtml(item.label)}</span>

            ${isBanner ? `
              <textarea class="item-expected-value ${isExists ? 'match-exists' : ''}" data-idx="${realIdx}" rows="3"
                        ${isExists ? 'readonly' : ''}
                        placeholder="${placeholderText}"
                        title="원본: ${escapeHtml(item.value)}">${escapeHtml(displayVal)}</textarea>
            ` : `
              <input type="text" class="item-expected-value ${isExists ? 'match-exists' : ''}" data-idx="${realIdx}" 
                     value="${escapeHtml(displayVal)}" 
                     ${isExists ? 'readonly' : ''}
                     placeholder="${placeholderText}"
                     title="원본: ${escapeHtml(item.value)}">
            `}
            
            <div class="item-controls">
              <select class="item-match-type" data-idx="${realIdx}">
                <option value="exists"   ${item.match_type==='exists'   ? 'selected':''}>exists (존재확인)</option>
                <option value="exact"    ${item.match_type==='exact'    ? 'selected':''}>exact (정확일치)</option>
                <option value="contains" ${item.match_type==='contains' ? 'selected':''}>contains (*CE1*)</option>
                <option value="regex"    ${item.match_type==='regex'    ? 'selected':''}>regex (^CE_)</option>
              </select>
              <button class="item-weight ${item.weight}" data-idx="${realIdx}">${item.weight}</button>
            </div>
          </div>
        `);
      });
    });

    list.innerHTML = htmlParts.join('');

    // 블록별 전체 선택/해제 이벤트
    list.querySelectorAll('.block-item-toggle').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const bid = btn.dataset.blockId;
        const val = btn.dataset.val === 'true';
        const block = parsedBlocks.find(b => b.block_id === bid);
        if (block) {
          block.enabled = val;
          const blockItemIds = new Set((block.items || []).map(i => i.id));
          combined.forEach(i => {
            if (blockItemIds.has(i.id)) {
              i.selected = val;
            }
          });
          renderBlocks();
          buildSectionFilters();
          renderItems();
          const selectedTotal = combined.filter(i => i.selected).length;
          document.getElementById('golden-item-count').textContent = selectedTotal;
          updateLivePreview();
        }
      });
    });
  } else {
    // 레거시 그룹핑 렌더링
    const filtered = filterSection
      ? combined.filter(i => i.section === filterSection)
      : combined;

    const grouped = {};
    filtered.forEach(item => {
      let sec = item.section || '기타';
      if (!grouped[sec]) grouped[sec] = [];
      grouped[sec].push(item);
    });

    const htmlParts = [];
    Object.keys(grouped).sort().forEach(sec => {
      htmlParts.push(`
        <div class="section-group-header flex justify-between items-center" style="background:var(--bg-secondary); padding:8px 12px; margin-top:16px; border-radius:4px; border-left:4px solid var(--accent);">
          <div>
            <strong>${escapeHtml(sec)}</strong>
            <span class="text-muted" style="font-size:11px">(${grouped[sec].length}개)</span>
          </div>
          <div class="flex gap-2">
            <button class="btn btn-secondary btn-sm section-toggle" data-sec="${sec}" data-val="true" style="padding:2px 8px; font-size:11px">전체 선택</button>
            <button class="btn btn-secondary btn-sm section-toggle" data-sec="${sec}" data-val="false" style="padding:2px 8px; font-size:11px">전체 해제</button>
          </div>
        </div>
      `);

      grouped[sec].forEach(item => {
        const realIdx = combined.indexOf(item);
        const isBanner = (item.section || '').toLowerCase() === 'banner';
        const isExists = item.match_type === 'exists';
        const valText = isExists 
          ? '(임의의 값 허용 - 존재 여부 확인)' 
          : (item.expected_value !== undefined ? item.expected_value : item.value);

        htmlParts.push(`
          <div class="item-row ${item.selected ? 'selected' : ''}" data-idx="${realIdx}">
            <input type="checkbox" class="item-check" data-idx="${realIdx}" ${item.selected ? 'checked' : ''}>
            <span class="item-label" title="${escapeHtml(item.label)}">${escapeHtml(item.label)}</span>
            ${isBanner ? `
              <textarea class="item-expected-value ${isExists ? 'match-exists' : ''}" data-idx="${realIdx}" rows="3"
                        ${isExists ? 'readonly' : ''}
                        style="flex:1; max-width:280px; font-family:'Fira Code', monospace; font-size:11px; background:var(--bg-primary); color:var(--text-primary); border:1px solid var(--border); border-radius:4px; padding:2px 6px; resize:vertical;">${escapeHtml(valText)}</textarea>
            ` : `
              <input type="text" class="item-expected-value ${isExists ? 'match-exists' : ''}" data-idx="${realIdx}" 
                     value="${escapeHtml(valText)}" 
                     ${isExists ? 'readonly' : ''}
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

    list.querySelectorAll('.section-toggle').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const sec = btn.dataset.sec;
        const val = btn.dataset.val === 'true';
        grouped[sec].forEach(i => i.selected = val);
        renderItems();
        const selectedTotal = combined.filter(i => i.selected).length;
        document.getElementById('golden-item-count').textContent = selectedTotal;
        updateLivePreview();
      });
    });
  }

  // 공통 이벤트 바인딩: 체크박스 변경 시
  list.querySelectorAll('.item-check').forEach(cb => {
    cb.addEventListener('change', () => {
      const idx = +cb.dataset.idx;
      combined[idx].selected = cb.checked;
      cb.closest('.item-row').classList.toggle('selected', cb.checked);

      // 블록 상태 및 필터 동기화
      const item = combined[idx];
      if (parsedBlocks && parsedBlocks.length > 0) {
        const block = parsedBlocks.find(b => (b.items || []).some(it => it.id === item.id));
        if (block) {
          const blockItems = combined.filter(i => (block.items || []).some(it => it.id === i.id));
          block.enabled = blockItems.some(i => i.selected);
          renderBlocks();
          buildSectionFilters();
        }
      }

      const selectedTotal = combined.filter(i => i.selected).length;
      document.getElementById('golden-item-count').textContent = selectedTotal;
      updateLivePreview();
    });
  });

  list.querySelectorAll('.item-match-type').forEach(sel => {
    sel.addEventListener('change', () => {
      const idx = +sel.dataset.idx;
      const item = combined[idx];
      item.match_type = sel.value;

      const row = sel.closest('.item-row');
      const ipt = row?.querySelector('.item-expected-value');
      if (ipt) {
        if (item.match_type === 'exists') {
          ipt.classList.add('match-exists');
          ipt.readOnly = true;
          ipt.value = '(임의의 값 허용 - 존재 여부 확인)';
          ipt.placeholder = '존재 여부만 검사 (어떤 값이든 허용)';
          ipt.title = '해당 명령어가 존재하기만 하면 어떤 값이든 합격';
        } else {
          ipt.classList.remove('match-exists');
          ipt.readOnly = false;
          ipt.value = item.expected_value !== undefined ? item.expected_value : item.value;
          if (item.match_type === 'contains') {
            ipt.placeholder = '예: *CE1* 또는 키워드';
            ipt.title = '*CE1* 또는 포함될 텍스트';
          } else if (item.match_type === 'regex') {
            ipt.placeholder = '예: ^CE_ (정규표현식)';
            ipt.title = '^CE_ 등 정규표현식 패턴';
          } else {
            ipt.placeholder = '정확한 기대값 입력 (예: 17.12)';
            ipt.title = `원본: ${item.value}`;
          }
        }
      }
      updateLivePreview();
    });
  });

  list.querySelectorAll('.item-weight').forEach(btn => {
    btn.addEventListener('click', () => {
      const idx = +btn.dataset.idx;
      combined[idx].weight = combined[idx].weight === 'required' ? 'optional' : 'required';
      btn.className = `item-weight ${combined[idx].weight}`;
      btn.textContent = combined[idx].weight;
      updateLivePreview();
    });
  });

  list.querySelectorAll('.item-expected-value').forEach(ipt => {
    ipt.addEventListener('input', () => {
      combined[+ipt.dataset.idx].expected_value = ipt.value;
      updateLivePreview();
    });
  });

  // 실시간 템플릿 프리뷰 즉시 갱신
  updateLivePreview();
}

function toggleAll(checked) {
  const combined = [...allItems, ...intfItems];
  if (parsedBlocks && parsedBlocks.length > 0) {
    const targetBlocks = filterBlock ? parsedBlocks.filter(b => b.block_id === filterBlock) : parsedBlocks;
    const targetBlockIds = new Set(targetBlocks.map(b => b.block_id));
    targetBlocks.forEach(b => b.enabled = checked);

    combined.forEach(item => {
      const block = parsedBlocks.find(b => (b.items || []).some(it => it.id === item.id));
      if (block && targetBlockIds.has(block.block_id)) {
        item.selected = checked;
      }
    });
    renderBlocks();
    buildSectionFilters();
    renderItems();
  } else {
    const filtered = filterSection
      ? combined.filter(i => i.section === filterSection)
      : combined;
    filtered.forEach(i => i.selected = checked);
    renderItems();
  }
  const selectedTotal = combined.filter(i => i.selected).length;
  document.getElementById('golden-item-count').textContent = selectedTotal;
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
    
    // 블록 데이터 복원
    if (tpl.golden_parsed && tpl.golden_parsed.blocks) {
      parsedBlocks = tpl.golden_parsed.blocks;
      document.getElementById('golden-blocks-card').style.display = 'block';
      renderBlocks();
    } else {
      document.getElementById('golden-blocks-card').style.display = 'none';
    }

    allItems = (tpl.golden_items || []).filter(i => !i.section?.startsWith('interface (')).map(i => ({ ...i, selected: true }));
    intfItems = (tpl.golden_items || []).filter(i => i.section?.startsWith('interface (')).map(i => ({ ...i, selected: true }));
    filterSection = '';

    document.getElementById('golden-section-count').textContent = parsedBlocks.length || '?';
    document.getElementById('golden-item-count').textContent = allItems.length + intfItems.length;
    document.getElementById('golden-results-area').style.display = 'block';
    document.getElementById('golden-cancel-btn').style.display = 'inline-block';

    buildSectionFilters();
    renderItems();
    updateLivePreview();
    toast('템플릿을 수정합니다.', 'info');
    window.scrollTo(0, 0);
  } catch (err) {
    toast(err.message, 'error');
  }
};

async function saveTemplate() {
  const combined = [...allItems, ...intfItems];
  if (!parsedData && combined.length === 0) return toast('먼저 설정 파일을 업로드하세요.', 'error');

  const name = document.getElementById('golden-template-name').value.trim();
  const regex = document.getElementById('golden-hostname-regex').value.trim();
  const desc = document.getElementById('golden-description').value.trim();

  if (!name) return toast('템플릿 이름을 입력하세요.', 'error');

  const selectedItems = combined.filter(i => i.selected).map(item => {
    const { parent, cmd } = getCommandInfo(item);
    return {
      id: item.id,
      block_id: item.block_id || item.section,
      section: item.section,
      parent_node: parent,
      command_line: cmd,
      label: item.label,
      value: item.value,
      expected_value: item.expected_value !== undefined ? item.expected_value : item.value,
      match_type: item.match_type || 'exact',
      weight: item.weight || 'required',
      source: item.source || 'cisco_config_parser',
      raw_block: item.raw_block || ''
    };
  });
  if (selectedItems.length === 0) return toast('최소 1개 항목을 선택하세요.', 'error');

  const btn = document.getElementById('golden-save-btn');
  setLoading(btn, true, '저장 중...');

  const osType = document.getElementById('golden-os-select').value;

  try {
    const goldenParsedToSave = parsedData?.parsed || {};
    goldenParsedToSave.blocks = parsedBlocks;

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
        golden_parsed: goldenParsedToSave,
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

// ── 실시간 최종 골든 템플릿 설정 프리뷰 ──────────────────────────────
function getCommandInfo(item) {
  let parent = (item.parent_node || '').trim();
  let cmd = (item.command_line || '').trim();

  if (!cmd) {
    if (item.label && item.label.includes(' > ')) {
      const parts = item.label.split(' > ');
      if (!parent) parent = parts[0].trim();
      cmd = parts.slice(1).join(' > ').trim();
    } else {
      cmd = (item.label || '').trim();
    }
  }

  // 인터페이스 섹션의 경우 부모가 'GigabitEthernet0/0/0' 처럼 이름만 있을 때 'interface ' 프리픽스 보정
  if (parent && (item.section === 'interfaces_l2' || item.section === 'interfaces_l3' || item.section === 'interfaces')) {
    if (!parent.toLowerCase().startsWith('interface ') && !parent.toLowerCase().startsWith('l2 ') && !parent.toLowerCase().startsWith('l3 ')) {
      parent = `interface ${parent}`;
    }
  }

  return { parent, cmd };
}

function formatCommandLine(item, baseCmd) {
  const mtype = item.match_type || 'exact';
  const val = item.expected_value !== undefined ? item.expected_value : item.value;
  const weightTag = item.weight === 'optional' ? ' [optional]' : '';

  let finalCmd = baseCmd;

  // exact 타입이면서 사용자가 기대값을 수정한 경우 명령어에 반영
  if (mtype === 'exact' && item.expected_value !== undefined && item.expected_value !== item.value) {
    const origVal = String(item.value || '').trim();
    const newVal = String(item.expected_value || '').trim();
    if (origVal && finalCmd.endsWith(origVal)) {
      finalCmd = finalCmd.slice(0, finalCmd.length - origVal.length) + newVal;
    } else if (origVal && finalCmd.includes(' ' + origVal)) {
      finalCmd = finalCmd.replace(' ' + origVal, ' ' + newVal);
    }
  }

  if (mtype === 'exists') {
    return `${finalCmd}  ! [exists: 임의값 허용/존재 확인${weightTag}]`;
  } else if (mtype === 'contains') {
    const cleanKw = String(val).replace(/^\*+|\*+$/g, '');
    return `${finalCmd}  ! [contains: *${cleanKw}*${weightTag}]`;
  } else if (mtype === 'regex') {
    return `${finalCmd}  ! [regex: /${val}/${weightTag}]`;
  } else {
    return weightTag ? `${finalCmd}  !${weightTag}` : finalCmd;
  }
}

export function updateLivePreview() {
  const codeEl = document.getElementById('golden-live-preview-code');
  const statsEl = document.getElementById('preview-active-stats');
  if (!codeEl) return;

  const combined = [...allItems, ...intfItems];
  const hostname = document.getElementById('golden-hostname')?.textContent || '(알 수 없음)';

  if (!parsedBlocks || parsedBlocks.length === 0) {
    const selectedItems = combined.filter(i => i.selected);
    if (statsEl) statsEl.textContent = `선택된 항목: ${selectedItems.length}개`;
    if (selectedItems.length === 0) {
      codeEl.textContent = '! 선택된 설정 항목이 없습니다. 상단에서 블록 또는 항목을 선택하세요.';
      return;
    }
    const lines = [
      `! ====================================================================`,
      `! Network Config Auditor - Golden Template Live Preview`,
      `! Hostname: ${hostname} | Total Selected: ${selectedItems.length} Items`,
      `! ====================================================================`,
      ``
    ];

    // 부모 그룹별로 정렬하여 실제 Cisco 설정 포맷으로 출력
    const parentGroups = [];
    const parentMap = new Map();
    selectedItems.forEach(item => {
      const { parent, cmd } = getCommandInfo(item);
      if (!parentMap.has(parent)) {
        const group = { parent, items: [] };
        parentMap.set(parent, group);
        parentGroups.push(group);
      }
      parentMap.get(parent).items.push({ item, cmd });
    });

    parentGroups.forEach(grp => {
      if (grp.parent) {
        lines.push(grp.parent);
        grp.items.forEach(({ item, cmd }) => {
          lines.push(` ${formatCommandLine(item, cmd)}`);
        });
        lines.push('!');
      } else {
        grp.items.forEach(({ item, cmd }) => {
          lines.push(formatCommandLine(item, cmd));
        });
      }
    });

    codeEl.textContent = lines.join('\n');
    return;
  }

  // 블록 순서대로 수집
  const activeBlocks = parsedBlocks.filter(b => b.enabled);
  let totalActiveItems = 0;
  const lines = [
    `! ====================================================================`,
    `! Network Config Auditor - Golden Template Live Preview`,
    `! Hostname: ${hostname} | Target Blocks: ${activeBlocks.length}개 / Items: (계산 중)`,
    `! ====================================================================`,
    ``
  ];

  activeBlocks.forEach((block, idx) => {
    const blockItemIds = new Set((block.items || []).map(i => i.id));
    const blockItems = combined.filter(i => blockItemIds.has(i.id) && i.selected);
    if (blockItems.length === 0) return;

    totalActiveItems += blockItems.length;
    lines.push(`! --------------------------------------------------`);
    lines.push(`! [Block #${block.order || (idx + 1)}] ${block.name} (${blockItems.length}개 항목)`);
    lines.push(`! --------------------------------------------------`);

    // 부모 노드별 그룹화 (실제 Cisco running-config 계층 구조 생성)
    const parentGroups = [];
    const parentMap = new Map();

    blockItems.forEach(item => {
      const { parent, cmd } = getCommandInfo(item);
      if (!parentMap.has(parent)) {
        const group = { parent, items: [] };
        parentMap.set(parent, group);
        parentGroups.push(group);
      }
      parentMap.get(parent).items.push({ item, cmd });
    });

    parentGroups.forEach(grp => {
      if (grp.parent) {
        lines.push(grp.parent);
        grp.items.forEach(({ item, cmd }) => {
          lines.push(` ${formatCommandLine(item, cmd)}`);
        });
        lines.push('!');
      } else {
        grp.items.forEach(({ item, cmd }) => {
          lines.push(formatCommandLine(item, cmd));
        });
      }
    });

    lines.push(``);
  });

  if (statsEl) {
    statsEl.textContent = `선택된 블록: ${activeBlocks.length}개 / 항목: ${totalActiveItems}개`;
  }
  lines[2] = `! Hostname: ${hostname} | Target Blocks: ${activeBlocks.length}개 / Items: ${totalActiveItems}개`;

  if (totalActiveItems === 0) {
    codeEl.textContent = '! 선택된 설정 항목이 없습니다. 상단에서 블록 또는 항목을 체크하세요.';
  } else {
    codeEl.textContent = lines.join('\n');
  }
}
