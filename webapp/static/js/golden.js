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

// ── Golden Drawer Global Handlers ──
window.openGoldenDrawer = (tpl = null) => {
  const drawer = document.getElementById('golden-drawer');
  const backdrop = document.getElementById('golden-drawer-backdrop');
  if (drawer) {
    drawer.classList.add('open');
    drawer.setAttribute('aria-hidden', 'false');
  }
  if (backdrop) backdrop.classList.add('open');

  const titleEl = document.getElementById('drawer-golden-title');
  const subEl = document.getElementById('drawer-golden-subtitle');
  const hostname = document.getElementById('golden-hostname')?.textContent || '';

  if (tpl) {
    if (titleEl) titleEl.textContent = `골든 템플릿 수정: ${tpl.name || ''}`;
    if (subEl) subEl.textContent = '기존 템플릿의 검사 룰 및 설정을 수정합니다.';
  } else {
    if (titleEl) titleEl.textContent = '새 골든 템플릿 생성';
    if (subEl) subEl.textContent = `${hostname ? `장비(${hostname}) 설정 기반으로 ` : ''}감사 기준 룰을 선택하고 저장하세요.`;
  }

  window.switchGoldenDrawerTab('rules');
  updateDrawerStats();
};

window.closeGoldenDrawer = () => {
  const drawer = document.getElementById('golden-drawer');
  const backdrop = document.getElementById('golden-drawer-backdrop');
  if (drawer) {
    drawer.classList.remove('open');
    drawer.setAttribute('aria-hidden', 'true');
  }
  if (backdrop) backdrop.classList.remove('open');
};

window.switchGoldenDrawerTab = (tabName) => {
  document.querySelectorAll('.golden-drawer-tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tabName);
  });
  document.querySelectorAll('.golden-tab-pane').forEach(pane => {
    pane.style.display = pane.id === `drawer-tab-${tabName}` ? 'block' : 'none';
  });
  if (tabName === 'preview') {
    updateLivePreview();
  }
};

export function updateDrawerStats() {
  const combined = [...allItems, ...intfItems];
  const count = combined.filter(i => i.selected).length;
  const countBadge = document.getElementById('golden-drawer-item-count');
  const footerStats = document.getElementById('golden-drawer-footer-stats');
  const mainCount = document.getElementById('golden-item-count');
  if (countBadge) countBadge.textContent = count;
  if (footerStats) footerStats.textContent = `선택된 항목: ${count}개 / 전체 ${combined.length}개`;
  if (mainCount) mainCount.textContent = count;
}

export function initGolden() {
  const zone    = document.getElementById('golden-drop-zone');
  const input   = document.getElementById('golden-file-input');
  const saveBtn = document.getElementById('golden-save-btn');
  const cancelBtn = document.getElementById('golden-cancel-btn');
  const selAll  = document.getElementById('golden-select-all');
  const selNone = document.getElementById('golden-select-none');
  const expandTreeBtn = document.getElementById('golden-tree-expand-all');
  const collapseTreeBtn = document.getElementById('golden-tree-collapse-all');

  if (zone && input) {
    initDropZone(zone, input, files => handleUnifiedUpload(files[0]));
  }

  // 드롭존 배너에도 파일 드롭 지원
  const banner = document.getElementById('golden-upload-banner');
  if (banner && input) {
    banner.addEventListener('dragover', e => { e.preventDefault(); banner.classList.add('drag-over'); });
    banner.addEventListener('dragleave', () => banner.classList.remove('drag-over'));
    banner.addEventListener('drop', e => {
      e.preventDefault();
      banner.classList.remove('drag-over');
      if (e.dataTransfer.files.length) handleUnifiedUpload(e.dataTransfer.files[0]);
    });
  }

  if (saveBtn) saveBtn.addEventListener('click', saveTemplate);
  if (cancelBtn) {
    cancelBtn.addEventListener('click', () => {
      currentEditingId = null;
      window.closeGoldenDrawer();
      toast('수정이 취소되었습니다.', 'info');
    });
  }
  if (selAll) selAll.addEventListener('click', () => toggleAll(true));
  if (selNone) selNone.addEventListener('click', () => toggleAll(false));

  // ESC 키로 골든 에디터 드로어 닫기
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      const drawer = document.getElementById('golden-drawer');
      if (drawer && drawer.classList.contains('open')) {
        window.closeGoldenDrawer();
      }
    }
  });

  // 실시간 프리뷰 복사 버튼
  const copyPreviewBtn = document.getElementById('preview-copy-btn');
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

  if (expandTreeBtn) {
    expandTreeBtn.addEventListener('click', () => {
      parsedBlocks.forEach(b => {
        b.collapsed = false;
        b.subCollapsed = {};
      });
      document.querySelectorAll('.tree-block-content, .tree-subgroup-content').forEach(el => el.classList.remove('collapsed'));
      document.querySelectorAll('.tree-expand-btn').forEach(btn => btn.classList.remove('collapsed'));
      toast('모든 설정 트리를 펼쳤습니다.', 'info');
    });
  }

  if (collapseTreeBtn) {
    collapseTreeBtn.addEventListener('click', () => {
      parsedBlocks.forEach(b => b.collapsed = true);
      document.querySelectorAll('.tree-block-content').forEach(el => el.classList.add('collapsed'));
      document.querySelectorAll('.tree-block-header .tree-expand-btn').forEach(btn => btn.classList.add('collapsed'));
      toast('모든 설정 트리를 접었습니다.', 'info');
    });
  }

  // 섹션/블록 필터 버튼 클릭
  const filtersEl = document.getElementById('golden-section-filters');
  if (filtersEl) {
    filtersEl.addEventListener('click', e => {
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
      match_type: item.match_type || (item.source === 'ciscoconfparse2' || item.source === 'cisco_config_parser' || item.source === 'genie' ? 'exact' : 'contains'),
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
    const nameInput = document.getElementById('golden-template-name');
    if (nameInput && !nameInput.value) {
      nameInput.value = data.hostname || file.name.replace(/\.[^/.]+$/, '');
    }

    const hostEl = document.getElementById('golden-hostname');
    if (hostEl) hostEl.textContent = data.hostname || '(알 수 없음)';
    const secEl = document.getElementById('golden-section-count');
    if (secEl) secEl.textContent = data.section_count;
    const itemEl = document.getElementById('golden-item-count');
    if (itemEl) itemEl.textContent = allItems.length + intfItems.length;
    
    // 인터페이스 요약 업데이트
    const totalEl = document.getElementById('intf-total-count');
    if (totalEl) totalEl.textContent = data.intf_summary.total;
    const upEl = document.getElementById('intf-uplink-count');
    if (upEl) upEl.textContent = data.intf_summary.uplink_count;
    const l2El = document.getElementById('intf-l2-count');
    if (l2El) l2El.textContent = data.intf_summary.l2_count;
    const summaryCard = document.getElementById('golden-intf-summary');
    if (summaryCard) summaryCard.style.display = 'block';
    
    // 블록 카드 상태
    const blocksCard = document.getElementById('golden-blocks-card');
    if (blocksCard) {
      blocksCard.style.display = parsedBlocks.length > 0 ? 'block' : 'none';
    }

    if (window.openGoldenDrawer) {
      window.openGoldenDrawer();
    }

    buildSectionFilters();
    renderItems();
    updateLivePreview();
    updateDrawerStats();

    zone.innerHTML = `
      <div class="drop-icon">✅</div>
      <h3>${file.name}</h3>
      <p>설정 분석 완료 — 오른쪽 에디터 드로어에서 세부 설정을 편집하세요</p>
    `;
    toast(isMerge ? '설정이 성공적으로 병합되었습니다.' : '설정 분석 완료! 에디터 창이 열렸습니다.', 'success');
  } catch (err) {
    zone.innerHTML = `
      <div class="drop-icon">📁+🔌</div>
      <h3>설정 파일을 드래그하거나 클릭하여 업로드</h3>
      <p>전체 설정 또는 인터페이스 설정 파일 (.cfg, .txt, .conf)</p>
    `;
    toast(`업로드 실패: ${err.message}`, 'error');
  }
}

// ── Drag & Drop 블록 (3-Tier 트리로 통합) ──────────────────────────

function renderBlocks() {
  // 블록 카드가 세부설정 3-Tier 계층 트리(renderItems)로 완전 통합되었습니다.
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
  intfItems.sort((a, b) => {
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
      html += `<button class="filter-btn ${isActive} ${isDisabled}" data-block="${b.block_id}">#${b.order} ${escapeHtml(b.name)} (${count})</button>`;
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

// ── 3계층 자식 리프 노드 렌더러 ────────────────────────────────────

function renderLeafRow(item, combined, hasParent, isLast) {
  const realIdx = combined.indexOf(item);
  const isBanner = (item.section || '').toLowerCase() === 'banner';
  const isExists = item.match_type === 'exists';
  const isFullLine = !!item.full_line_mode;
  const isSelected = !!item.selected;

  const branchSymbol = hasParent ? (isLast ? '└── ' : '├── ') : '📄 ';
  const displayLabel = item.command_line || item.label;
  const fullCmd = item.command_line || item.label;

  const valText = isFullLine
    ? (item.expected_line !== undefined ? item.expected_line : fullCmd)
    : (item.expected_value !== undefined ? item.expected_value : item.value);

  const displayVal = isExists ? '(임의의 값 허용 - 존재 여부 확인)' : valText;
  const placeholderText = isFullLine
    ? '명령어 전체 라인 직접 편집 (예: standby 1 preempt delay minimum 30 reload 60)'
    : (item.match_type === 'contains' 
      ? '예: *CE1* 또는 키워드' 
      : item.match_type === 'regex' 
      ? '예: ^CE_ (정규표현식)' 
      : item.match_type === 'exists' 
      ? '존재 여부만 검사 (어떤 값이든 허용)' 
      : '정확한 기대값 입력 (예: 17.12)');

  return `
    <div class="tree-leaf-row ${isSelected ? 'selected' : 'unselected'} ${isFullLine ? 'full-line-mode' : ''}" data-idx="${realIdx}">
      <span class="tree-branch-symbol">${branchSymbol}</span>
      <input type="checkbox" class="item-check" data-idx="${realIdx}" ${isSelected ? 'checked' : ''} title="${isSelected ? '검사 대상 포함 (체크 해제 시 취소선 및 제외)' : '검사 제외됨 (체크 시 규칙에 다시 포함)'}">
      
      ${isFullLine ? `
        <span class="badge-full-tag" title="전체 라인 직접 편집 모드 활성화됨">전체라인</span>
      ` : `
        <span class="tree-leaf-label ${!isSelected ? 'strikethrough' : ''}" title="${escapeHtml(item.label || displayLabel)}">${escapeHtml(displayLabel)}</span>
      `}

      ${isBanner ? `
        <textarea class="item-expected-value ${isFullLine ? 'full-line-input' : ''} ${isExists ? 'match-exists' : ''}" data-idx="${realIdx}" rows="2"
                  ${isExists ? 'readonly' : ''}
                  placeholder="${placeholderText}"
                  title="${isFullLine ? '전체 배너 내용 직접 편집' : '원본: ' + escapeHtml(item.value)}">${escapeHtml(displayVal)}</textarea>
      ` : `
        <input type="text" class="item-expected-value ${isFullLine ? 'full-line-input' : ''} ${isExists ? 'match-exists' : ''}" data-idx="${realIdx}" 
               value="${escapeHtml(displayVal)}" 
               ${isExists ? 'readonly' : ''}
               placeholder="${placeholderText}"
               title="${isFullLine ? '명령어 전체 라인 직접 편집' : '원본: ' + escapeHtml(item.value)}">
      `}
      
      <div class="item-controls">
        <button class="item-full-line-btn ${isFullLine ? 'active' : ''}" data-idx="${realIdx}" 
                title="${isFullLine ? '기본(값만 편집) 모드로 전환' : '명령어 전체 라인 직접 편집 모드로 전환'}">
          ${isFullLine ? '📝 라인모드' : '✏️ 전체라인'}
        </button>
        <select class="item-match-type form-select" data-idx="${realIdx}">
          <option value="exists"   ${item.match_type==='exists'   ? 'selected':''}>exists (존재확인)</option>
          <option value="exact"    ${item.match_type==='exact'    ? 'selected':''}>exact (정확일치)</option>
          <option value="contains" ${item.match_type==='contains' ? 'selected':''}>contains (*CE1*)</option>
          <option value="regex"    ${item.match_type==='regex'    ? 'selected':''}>regex (^CE_)</option>
        </select>
        <button class="item-weight ${item.weight}" data-idx="${realIdx}" title="가중치 토글 (required / optional)">${item.weight}</button>
      </div>
    </div>
  `;
}

// ── 상세 항목 3-Tier 계층형 트리 렌더링 ─────────────────────────────

function renderItems() {
  const list = document.getElementById('golden-items-list');
  if (!list) return;
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
      const isAllSelected = selectedCount === blockItems.length;
      const isPartSelected = selectedCount > 0 && selectedCount < blockItems.length;
      const realBlockIdx = parsedBlocks.indexOf(block);

      // 서브그룹 분류 (Tier 2: parent_node 기준, 단독 인터페이스 등 중복 방지)
      const subgroups = {};
      const standaloneItems = [];
      blockItems.forEach(item => {
        let pNode = (item.parent_node || '').trim();
        let cLine = (item.command_line || item.label || '').trim();
        if (pNode && cLine && pNode.toLowerCase() === cLine.toLowerCase()) {
          pNode = '';
        }
        if (pNode) {
          if (!subgroups[pNode]) subgroups[pNode] = [];
          subgroups[pNode].push(item);
        } else {
          standaloneItems.push(item);
        }
      });

      htmlParts.push(`
        <div class="tree-block-group ${!block.enabled ? 'disabled-group' : ''}" 
             draggable="true" 
             data-block-id="${block.block_id}" 
             data-block-index="${realBlockIdx}">
          
          <!-- Tier 1: 블록 헤더 (전체 Drag & Drop 가능) -->
          <div class="tree-block-header">
            <div class="tree-drag-handle" title="끌어서 감사 순서 변경">⋮⋮</div>
            <button class="tree-expand-btn ${block.collapsed ? 'collapsed' : ''}" data-block-id="${block.block_id}" title="블록 접기/펼치기">▼</button>
            <span class="block-order-badge">#${block.order || (bIdx + 1)}</span>
            <input type="checkbox" class="tree-block-check" data-block-id="${block.block_id}" 
                   ${isAllSelected ? 'checked' : ''} 
                   ${isPartSelected ? 'data-indeterminate="true"' : ''}
                   title="블록 전체 선택/해제">
            
            <span class="tree-block-title">
              <span>${escapeHtml(block.name)}</span>
              <span class="text-muted text-xs">(${selectedCount}/${blockItems.length}개 선택됨)</span>
            </span>

            <div class="flex gap-2 items-center" style="margin-left:auto;">
              <button class="btn btn-secondary btn-sm block-item-toggle" data-block-id="${block.block_id}" data-val="true" style="padding:2px 8px; font-size:11px">전체 선택</button>
              <button class="btn btn-secondary btn-sm block-item-toggle" data-block-id="${block.block_id}" data-val="false" style="padding:2px 8px; font-size:11px">전체 해제</button>
            </div>
          </div>

          <!-- Tier 1 콘텐츠 (서브그룹 및 리프 명령어들) -->
          <div class="tree-block-content ${block.collapsed ? 'collapsed' : ''}">
            
            ${(block.block_id === 'interfaces_l2' || block.block_id === 'interfaces_l3') ? `
              <div class="intf-delegation-tip card" style="margin: 8px 10px 14px 10px; padding: 10px 14px; background: rgba(88, 166, 255, 0.08); border: 1px solid rgba(88, 166, 255, 0.3); border-radius: 6px;">
                <div class="flex items-center justify-between flex-wrap gap-2">
                  <div class="flex items-start gap-2" style="font-size: 11.5px; color: var(--text-primary); line-height: 1.4;">
                    <span style="font-size: 15px;">💡</span>
                    <div>
                      <strong>인터페이스 정책 위임 권장:</strong> 수십 개의 물리 포트를 개별 고정 체크하는 대신, <a href="#" class="intf-goto-profiles-link" style="color:var(--accent); text-decoration:underline; font-weight:600;">[🏷️ 인터페이스 정책]</a> 탭을 사용하면 기종/포트 번호에 무관하게 모든 인터페이스를 일괄 동적 감사할 수 있습니다.
                    </div>
                  </div>
                  <div class="flex items-center gap-2">
                    <button class="btn btn-secondary btn-sm block-delegate-profiles-btn" data-block-id="${block.block_id}" style="font-size:11px; padding: 3px 8px; color: var(--accent); border-color: rgba(88, 166, 255, 0.4);" title="현재 블록의 물리 포트 설정을 모두 해제하여 인터페이스 정책 프로파일로 자동 위임합니다.">
                      🏷️ 인터페이스 정책으로 위임 (선택 해제)
                    </button>
                    <button class="btn btn-secondary btn-sm block-goto-profiles-btn" style="font-size:11px; padding: 3px 8px;">
                      정책 설정 바로가기 ↗
                    </button>
                  </div>
                </div>
              </div>
            ` : ''}

            <!-- 단독 상위 명령어들 -->
            ${standaloneItems.map((item, idx) => renderLeafRow(item, combined, false, idx === standaloneItems.length - 1)).join('')}

            <!-- Tier 2: 부모 노드 서브그룹들 (예: interface, router bgp) -->
            ${Object.entries(subgroups).map(([parentNode, subItems]) => {
              block.subCollapsed = block.subCollapsed || {};
              const isSubCollapsed = !!block.subCollapsed[parentNode];
              const subSelectedCount = subItems.filter(i => i.selected).length;
              const isSubAllSelected = subSelectedCount === subItems.length;

              return `
                <div class="tree-subgroup">
                  <div class="tree-subgroup-header" data-block-id="${block.block_id}" data-parent="${escapeHtml(parentNode)}">
                    <button class="tree-expand-btn ${isSubCollapsed ? 'collapsed' : ''}" style="margin-right:2px;">▼</button>
                    <input type="checkbox" class="tree-subgroup-check" data-block-id="${block.block_id}" data-parent="${escapeHtml(parentNode)}"
                           ${isSubAllSelected ? 'checked' : ''} title="서브그룹 전체 선택/해제">
                    <span style="font-weight:600;">📂 ${escapeHtml(parentNode)}</span>
                    <span class="badge text-xs" style="margin-left:auto; opacity:0.8;">${subSelectedCount}/${subItems.length}개</span>
                  </div>

                  <!-- Tier 3: 자식 명령어 리프 노드들 -->
                  <div class="tree-subgroup-content ${isSubCollapsed ? 'collapsed' : ''}">
                    ${subItems.map((item, idx) => renderLeafRow(item, combined, true, idx === subItems.length - 1)).join('')}
                  </div>
                </div>
              `;
            }).join('')}

          </div>
        </div>
      `);
    });

    list.innerHTML = htmlParts.join('');

    // indeterminate 체크박스 상태 적용
    list.querySelectorAll('.tree-block-check[data-indeterminate="true"]').forEach(cb => {
      cb.indeterminate = true;
    });

    // ── 이벤트 바인딩 1: 블록 전체 Drag & Drop 순서 변경 ──────────
    const blockGroups = list.querySelectorAll('.tree-block-group');
    blockGroups.forEach(group => {
      group.addEventListener('dragstart', (e) => {
        // 자식 콘텐츠(리프 노드/서브그룹) 또는 입력 필드 조작 시 드래그 방지
        if (e.target.closest('.tree-block-content, input, select, textarea, button')) {
          e.preventDefault();
          return;
        }
        draggedBlockIndex = +group.dataset.blockIndex;
        group.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', String(draggedBlockIndex));
      });

      group.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        group.classList.add('drag-over');
      });

      group.addEventListener('dragleave', () => {
        group.classList.remove('drag-over');
      });

      group.addEventListener('drop', (e) => {
        e.preventDefault();
        group.classList.remove('drag-over');
        const targetIndex = +group.dataset.blockIndex;
        if (draggedBlockIndex === null || draggedBlockIndex === targetIndex) return;

        const movedBlock = parsedBlocks.splice(draggedBlockIndex, 1)[0];
        parsedBlocks.splice(targetIndex, 0, movedBlock);

        // 순서 번호 재부여 (1, 2, 3...)
        parsedBlocks.forEach((b, i) => b.order = i + 1);

        // 전체 아이템 순서 재정렬
        reorderItemsByBlocks();

        draggedBlockIndex = null;
        renderItems();
        buildSectionFilters();
        updateLivePreview();
        toast(`블록 [${movedBlock.name}] 감사 순서가 #${targetIndex + 1}(으)로 변경되었습니다.`, 'info');
      });

      group.addEventListener('dragend', () => {
        group.classList.remove('dragging');
        blockGroups.forEach(g => g.classList.remove('drag-over'));
        draggedBlockIndex = null;
      });
    });

    // ── 이벤트 바인딩 2: 블록 접기/펼치기 ────────────────────────
    list.querySelectorAll('.tree-block-header').forEach(hdr => {
      hdr.addEventListener('click', (e) => {
        if (e.target.closest('input, button, .tree-drag-handle')) return;
        const group = hdr.closest('.tree-block-group');
        const bid = group.dataset.blockId;
        const block = parsedBlocks.find(b => b.block_id === bid);
        if (block) {
          block.collapsed = !block.collapsed;
          group.querySelector('.tree-block-content').classList.toggle('collapsed', block.collapsed);
          hdr.querySelector('.tree-expand-btn').classList.toggle('collapsed', block.collapsed);
        }
      });
    });

    list.querySelectorAll('.tree-block-header .tree-expand-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const group = btn.closest('.tree-block-group');
        const bid = group.dataset.blockId;
        const block = parsedBlocks.find(b => b.block_id === bid);
        if (block) {
          block.collapsed = !block.collapsed;
          group.querySelector('.tree-block-content').classList.toggle('collapsed', block.collapsed);
          btn.classList.toggle('collapsed', block.collapsed);
        }
      });
    });

    // ── 이벤트 바인딩 3: 서브그룹 접기/펼치기 ────────────────────
    list.querySelectorAll('.tree-subgroup-header').forEach(subHdr => {
      subHdr.addEventListener('click', (e) => {
        if (e.target.closest('input')) return;
        const parentNode = subHdr.dataset.parent;
        const bid = subHdr.dataset.blockId;
        const block = parsedBlocks.find(b => b.block_id === bid);
        const content = subHdr.nextElementSibling;
        const arrow = subHdr.querySelector('.tree-expand-btn');
        const isCollapsed = content.classList.toggle('collapsed');
        arrow.classList.toggle('collapsed', isCollapsed);
        if (block) {
          block.subCollapsed = block.subCollapsed || {};
          block.subCollapsed[parentNode] = isCollapsed;
        }
      });
    });

    // ── 이벤트 바인딩 4: 블록 체크박스 및 전체 선택/해제 ───────────
    list.querySelectorAll('.tree-block-check').forEach(cb => {
      cb.addEventListener('change', (e) => {
        e.stopPropagation();
        const bid = cb.dataset.blockId;
        const block = parsedBlocks.find(b => b.block_id === bid);
        if (block) {
          block.enabled = cb.checked;
          const blockItemIds = new Set((block.items || []).map(i => i.id));
          combined.forEach(item => {
            if (blockItemIds.has(item.id)) {
              item.selected = cb.checked;
            }
          });
          renderItems();
          buildSectionFilters();
          const selectedTotal = combined.filter(i => i.selected).length;
          document.getElementById('golden-item-count').textContent = selectedTotal;
          updateLivePreview();
        }
      });
    });

    list.querySelectorAll('.block-item-toggle').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const bid = btn.dataset.blockId;
        const val = btn.dataset.val === 'true';
        const block = parsedBlocks.find(b => b.block_id === bid);
        if (block) {
          block.enabled = val;
          const blockItemIds = new Set((block.items || []).map(i => i.id));
          combined.forEach(item => {
            if (blockItemIds.has(item.id)) {
              item.selected = val;
            }
          });
          renderItems();
          buildSectionFilters();
          const selectedTotal = combined.filter(i => i.selected).length;
          document.getElementById('golden-item-count').textContent = selectedTotal;
          updateLivePreview();
        }
      });
    });

    // ── 이벤트 바인딩 5: 서브그룹 체크박스 ─────────────────────────
    list.querySelectorAll('.tree-subgroup-check').forEach(cb => {
      cb.addEventListener('change', (e) => {
        e.stopPropagation();
        const bid = cb.dataset.blockId;
        const parentNode = cb.dataset.parent;
        const block = parsedBlocks.find(b => b.block_id === bid);
        const blockItemIds = new Set((block.items || []).map(i => i.id));
        combined.forEach(item => {
          if (blockItemIds.has(item.id) && item.parent_node === parentNode) {
            item.selected = cb.checked;
          }
        });
        renderItems();
        buildSectionFilters();
        const selectedTotal = combined.filter(i => i.selected).length;
        document.getElementById('golden-item-count').textContent = selectedTotal;
        updateLivePreview();
      });
    });

    // ── 이벤트 바인딩 6: 인터페이스 정책 프로파일 위임 및 탭 이동 ──
    list.querySelectorAll('.block-delegate-profiles-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const bid = btn.dataset.blockId;
        const block = parsedBlocks.find(b => b.block_id === bid);
        if (block) {
          block.enabled = false;
          const blockItemIds = new Set((block.items || []).map(i => i.id));
          combined.forEach(item => {
            if (blockItemIds.has(item.id)) {
              item.selected = false;
            }
          });
          renderItems();
          buildSectionFilters();
          const selectedTotal = combined.filter(i => i.selected).length;
          document.getElementById('golden-item-count').textContent = selectedTotal;
          updateLivePreview();
          toast(`[${block.name}] 설정을 모두 해제하여 [인터페이스 정책 프로파일]로 위임했습니다.`, 'success');
        }
      });
    });

    list.querySelectorAll('.block-goto-profiles-btn, .intf-goto-profiles-link').forEach(el => {
      el.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (window.switchGoldenDrawerTab) {
          window.switchGoldenDrawerTab('profiles');
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

      grouped[sec].forEach((item, idx) => {
        htmlParts.push(renderLeafRow(item, combined, false, idx === grouped[sec].length - 1));
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

  // ── 공통 이벤트 바인딩: 리프 아이템 ─────────────────────────────
  list.querySelectorAll('.item-check').forEach(cb => {
    cb.addEventListener('change', () => {
      const idx = +cb.dataset.idx;
      combined[idx].selected = cb.checked;
      const row = cb.closest('.tree-leaf-row');
      if (row) {
        row.classList.toggle('selected', cb.checked);
        row.classList.toggle('unselected', !cb.checked);
        const lbl = row.querySelector('.tree-leaf-label');
        if (lbl) lbl.classList.toggle('strikethrough', !cb.checked);
      }

      // 블록 활성화 상태 동기화
      const item = combined[idx];
      if (parsedBlocks && parsedBlocks.length > 0) {
        const block = parsedBlocks.find(b => (b.items || []).some(it => it.id === item.id));
        if (block) {
          const blockItems = combined.filter(i => (block.items || []).some(it => it.id === i.id));
          block.enabled = blockItems.some(i => i.selected);
          buildSectionFilters();
        }
      }

      const selectedTotal = combined.filter(i => i.selected).length;
      document.getElementById('golden-item-count').textContent = selectedTotal;
      updateDrawerStats();
      updateLivePreview();
    });
  });

  list.querySelectorAll('.item-match-type').forEach(sel => {
    sel.addEventListener('change', () => {
      const idx = +sel.dataset.idx;
      const item = combined[idx];
      item.match_type = sel.value;

      const row = sel.closest('.tree-leaf-row');
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

  // ── 이벤트 바인딩: 전체 라인 직접 편집 토글 버튼 ─────────────
  list.querySelectorAll('.item-full-line-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const idx = +btn.dataset.idx;
      const item = combined[idx];
      item.full_line_mode = !item.full_line_mode;
      const fullCmd = item.command_line || item.label;
      if (item.full_line_mode) {
        if (item.expected_line === undefined) {
          item.expected_line = fullCmd;
        }
        item.expected_value = item.expected_line;
        toast(`[${fullCmd}] 전체 라인 직접 편집 모드 ON`, 'info');
      } else {
        item.expected_value = item.value;
        toast(`[${fullCmd}] 기본 값 편집 모드로 복귀`, 'info');
      }
      renderItems();
      updateLivePreview();
    });
  });

  list.querySelectorAll('.item-expected-value').forEach(ipt => {
    ipt.addEventListener('input', () => {
      const idx = +ipt.dataset.idx;
      const item = combined[idx];
      if (item.full_line_mode) {
        item.expected_line = ipt.value;
        item.expected_value = ipt.value;
      } else {
        item.expected_value = ipt.value;
      }
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
  updateDrawerStats();
  updateLivePreview();
}

window.editTemplate = async (id) => {
  try {
    const res = await fetch(`/api/golden/templates/${id}`);
    if (!res.ok) throw new Error('템플릿을 불러오지 못했습니다.');
    const tpl = await res.json();

    currentEditingId = tpl.id;
    window._currentInterfaceProfiles = Array.isArray(tpl.interface_profiles) ? JSON.parse(JSON.stringify(tpl.interface_profiles)) : [];
    if (window.renderInterfaceProfiles) window.renderInterfaceProfiles();
    if (window.updateProfileTabBadge) window.updateProfileTabBadge();

    const nameInput = document.getElementById('golden-template-name');
    if (nameInput) nameInput.value = tpl.name || '';
    const descInput = document.getElementById('golden-description');
    if (descInput) descInput.value = tpl.description || '';
    const osSelect = document.getElementById('golden-os-select');
    if (osSelect) osSelect.value = tpl.os || 'iosxe';

    parsedData = { parsed: tpl.golden_parsed || {}, hostname: tpl.name || 'from template', items: [] };

    // 1. 블록 데이터 복원
    if (tpl.golden_parsed && Array.isArray(tpl.golden_parsed.blocks) && tpl.golden_parsed.blocks.length > 0) {
      parsedBlocks = tpl.golden_parsed.blocks.map((b, idx) => ({
        ...b,
        order: b.order || (idx + 1),
        enabled: b.enabled !== undefined ? b.enabled : true,
        collapsed: false,
        subCollapsed: {}
      }));
    } else {
      // 블록 정보가 없는 이전 템플릿의 경우 golden_items 기반 블록 자동 재구성
      const blockMap = new Map();
      (tpl.golden_items || []).forEach(item => {
        const bid = item.block_id || item.section || 'General';
        if (!blockMap.has(bid)) {
          blockMap.set(bid, {
            block_id: bid,
            name: item.section || bid,
            order: blockMap.size + 1,
            enabled: true,
            collapsed: false,
            subCollapsed: {},
            items: []
          });
        }
        blockMap.get(bid).items.push(item);
      });
      parsedBlocks = Array.from(blockMap.values());
    }

    // 2. 항목 데이터 완전 복원 (이전에 선택하지 않았던 항목도 취소선 상태로 복원하여 재선택 가능하게 함)
    const isIntf = (i) => i.section === 'interfaces_l2' || i.section === 'interfaces_l3' || (i.section && i.section.startsWith('interface'));
    
    const savedItemMap = new Map((tpl.golden_items || []).map(i => [i.id, i]));
    const restoredItems = [];
    const seenItemIds = new Set();

    if (tpl.golden_parsed && Array.isArray(tpl.golden_parsed.blocks) && tpl.golden_parsed.blocks.length > 0) {
      // 1) 원본 블록 내 모든 항목을 순회하며 복원
      tpl.golden_parsed.blocks.forEach(block => {
        (block.items || []).forEach(rawItem => {
          if (seenItemIds.has(rawItem.id)) return;
          seenItemIds.add(rawItem.id);

          const saved = savedItemMap.get(rawItem.id);
          if (saved) {
            // 이전에 선택되어 저장된 항목: 활성화 상태
            restoredItems.push({
              ...rawItem,
              ...saved,
              selected: saved.selected !== undefined ? saved.selected : true,
              expected_value: saved.expected_value !== undefined ? saved.expected_value : (saved.value !== undefined ? saved.value : rawItem.value),
              full_line_mode: !!saved.full_line_mode,
              expected_line: saved.expected_line || (saved.full_line_mode ? saved.command_line : undefined),
              match_type: saved.match_type || 'exact',
              weight: saved.weight || 'required'
            });
            savedItemMap.delete(rawItem.id);
          } else {
            // 이전에 선택하지 않아 제외되었던 항목: 미선택(취소선) 상태로 복원
            restoredItems.push({
              ...rawItem,
              selected: false,
              expected_value: rawItem.value !== undefined ? rawItem.value : '',
              full_line_mode: false,
              expected_line: rawItem.command_line,
              match_type: rawItem.match_type || 'exact',
              weight: rawItem.weight || 'required'
            });
          }
        });
      });

      // 2) 블록 항목 외에 추가로 저장되어 있던 항목 포함
      for (const [id, saved] of savedItemMap.entries()) {
        if (!seenItemIds.has(id)) {
          seenItemIds.add(id);
          restoredItems.push({
            ...saved,
            selected: saved.selected !== undefined ? saved.selected : true,
            expected_value: saved.expected_value !== undefined ? saved.expected_value : saved.value,
            full_line_mode: !!saved.full_line_mode,
            expected_line: saved.expected_line || (saved.full_line_mode ? saved.command_line : undefined),
            match_type: saved.match_type || 'exact',
            weight: saved.weight || 'required'
          });
        }
      }
    } else {
      (tpl.golden_items || []).forEach(item => {
        restoredItems.push({
          ...item,
          selected: item.selected !== undefined ? item.selected : true,
          expected_value: item.expected_value !== undefined ? item.expected_value : item.value,
          full_line_mode: !!item.full_line_mode,
          expected_line: item.expected_line || (item.full_line_mode ? item.command_line : undefined)
        });
      });
    }

    allItems = restoredItems.filter(i => !isIntf(i));
    intfItems = restoredItems.filter(i => isIntf(i));
    filterBlock = '';

    // 블록 활성화 상태 동기화 (블록 내 선택된 항목이 1개라도 있으면 활성화)
    parsedBlocks.forEach(b => {
      const bItemIds = new Set((b.items || []).map(i => i.id));
      b.enabled = restoredItems.some(i => bItemIds.has(i.id) && i.selected);
    });

    // 3. UI 카운트 및 표시 복원
    const hostEl = document.getElementById('golden-hostname');
    if (hostEl) hostEl.textContent = tpl.name || '(템플릿)';
    const secEl = document.getElementById('golden-section-count');
    if (secEl) secEl.textContent = parsedBlocks.length;
    const selectedCount = restoredItems.filter(i => i.selected).length;
    const itemEl = document.getElementById('golden-item-count');
    if (itemEl) itemEl.textContent = selectedCount;

    const intfTotal = document.getElementById('intf-total-count');
    if (intfTotal) intfTotal.textContent = intfItems.filter(i => i.selected).length;
    const intfSummaryCard = document.getElementById('golden-intf-summary');
    if (intfSummaryCard) intfSummaryCard.style.display = intfItems.length > 0 ? 'block' : 'none';

    if (window.openGoldenDrawer) {
      window.openGoldenDrawer(tpl);
    }

    buildSectionFilters();
    renderItems();
    updateLivePreview();
    updateDrawerStats();
    toast(`템플릿 "${tpl.name}"을(를) 편집 드로어에 불러왔습니다.`, 'info');
  } catch (err) {
    console.error('editTemplate error:', err);
    toast(`템플릿 불러오기 실패: ${err.message}`, 'error');
  }
};

async function saveTemplate() {
  const combined = [...allItems, ...intfItems];
  if (!parsedData && combined.length === 0) return toast('먼저 설정 파일을 업로드하거나 템플릿을 불러오세요.', 'error');

  const nameInput = document.getElementById('golden-template-name');
  const name = nameInput ? nameInput.value.trim() : '';
  const descInput = document.getElementById('golden-description');
  const desc = descInput ? descInput.value.trim() : '';

  if (!name) return toast('템플릿 이름을 입력하세요.', 'error');

  const selectedItems = combined.filter(i => i.selected).map(item => {
    const { parent, cmd } = getCommandInfo(item);
    const finalCmdLine = item.full_line_mode && item.expected_line ? item.expected_line : cmd;
    return {
      id: item.id,
      block_id: item.block_id || item.section,
      section: item.section,
      parent_node: parent,
      command_line: finalCmdLine,
      full_line_mode: !!item.full_line_mode,
      expected_line: item.expected_line || finalCmdLine,
      label: item.full_line_mode && item.expected_line ? item.expected_line : item.label,
      value: item.value,
      expected_value: item.full_line_mode ? (item.expected_line || finalCmdLine) : (item.expected_value !== undefined ? item.expected_value : item.value),
      match_type: item.match_type || 'exact',
      weight: item.weight || 'required',
      source: item.source || 'ciscoconfparse2',
      raw_block: item.raw_block || ''
    };
  });
  if (selectedItems.length === 0) return toast('최소 1개 항목을 선택하세요.', 'error');

  const btn = document.getElementById('golden-save-btn');
  setLoading(btn, true, '저장 중...');

  const osType = document.getElementById('golden-os-select').value;

  try {
    const goldenParsedToSave = parsedData?.parsed || {};
    const saveRes = await api('/api/golden/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name,
        hostname_regex: '',
        description: desc,
        os_type: osType,
        selected_items: selectedItems,
        conditional_rules: [],
        interface_profiles: window._currentInterfaceProfiles || [],
        golden_parsed: goldenParsedToSave,
        template_id: currentEditingId,
      }),
    });

    const savedId = saveRes.template_id;
    const hasPending = !!saveRes.has_pending_change;
    const affectedCount = saveRes.affected_count || 0;

    if (hasPending) {
      toast(`⚠️ 골든 템플릿 "${name}" 수정 완료: Compare 연동 장비 ${affectedCount}대에 영향이 감지되어 변경 승인 대기 상태로 등록되었습니다.`, 'warning');
    } else {
      toast(`골든 템플릿 "${name}" 저장 완료`, 'success');
    }

    // 상태 초기화
    if (nameInput) nameInput.value = '';
    if (descInput) descInput.value = '';
    currentEditingId = null;
    const cancelBtn = document.getElementById('golden-cancel-btn');
    if (cancelBtn) cancelBtn.style.display = 'none';

    if (window.closeGoldenDrawer) {
      window.closeGoldenDrawer();
    }

    if (window.loadGoldenTemplates) {
      window.loadGoldenTemplates();
    }
    if (window.checkPendingTemplateChanges) {
      await window.checkPendingTemplateChanges();
    }
    if (window.loadCompareTree) {
      window.loadCompareTree();
    }

    // 변경사항에 영향을 받는 Compare 장비가 있는 경우 즉시 영향도 분석 모달 열기
    if (hasPending && window.openTemplateImpactModal) {
      setTimeout(() => {
        window.openTemplateImpactModal(savedId);
      }, 350);
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

  // 부모와 명령어가 동일한 경우(단독 인터페이스 등 중복 방지)
  if (parent && cmd && parent.toLowerCase() === cmd.toLowerCase()) {
    parent = '';
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

  // 전체 라인 직접 편집 모드인 경우 사용자가 입력한 전체 라인을 우선 사용
  if (item.full_line_mode && item.expected_line !== undefined) {
    finalCmd = item.expected_line;
  } else if (mtype === 'exact' && item.expected_value !== undefined && item.expected_value !== item.value) {
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
          if (!cmd || (grp.parent && cmd.toLowerCase() === grp.parent.toLowerCase())) return;
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
          if (!cmd || (grp.parent && cmd.toLowerCase() === grp.parent.toLowerCase())) return;
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

// ════════════════════════════════════════════════════════════════════════
// 인터페이스 정책 프로파일 (Interface Policy Profiles) UI 핸들러
// ════════════════════════════════════════════════════════════════════════

window._currentInterfaceProfiles = [];
window._modalCurrentRules = [];

window.updateProfileTabBadge = () => {
  const badge = document.getElementById('golden-drawer-profile-count');
  if (badge) {
    badge.textContent = window._currentInterfaceProfiles.length;
  }
};

window.renderInterfaceProfiles = () => {
  const container = document.getElementById('golden-profiles-list');
  if (!container) return;

  const profiles = window._currentInterfaceProfiles || [];
  if (profiles.length === 0) {
    container.innerHTML = `
      <div class="empty-state" style="padding:28px 16px; text-align:center; background:rgba(255,255,255,0.02); border:1px dashed var(--border); border-radius:8px;">
        <div style="font-size:28px; margin-bottom:8px;">🏷️</div>
        <div style="font-size:13px; font-weight:600; color:var(--text-secondary); margin-bottom:4px;">등록된 인터페이스 정책 프로파일이 없습니다.</div>
        <p class="text-muted text-xs" style="max-width:480px; margin:0 auto 12px;">전체 L2/L3 인터페이스를 대변하는 공통 룰이나, Description 패턴(예: UPLINK, AP)에 따라 꼭 들어가야 할 룰셋을 정의하세요.</p>
        <button class="btn btn-primary btn-sm" onclick="window.openProfileModal()">➕ 새 프로파일 추가</button>
      </div>
    `;
    return;
  }

  container.innerHTML = profiles.map(prof => {
    const targetType = prof.target_type || 'any';
    const typeLabel = targetType === 'l2' ? 'L2 스위치포트' : targetType === 'l3' ? 'L3 라우티드' : '전체 인터페이스';
    const typeColor = targetType === 'l2' ? '#58a6ff' : targetType === 'l3' ? '#3fb950' : '#d2a8ff';
    const typeBg = targetType === 'l2' ? 'rgba(88,166,255,0.1)' : targetType === 'l3' ? 'rgba(63,185,80,0.1)' : 'rgba(210,168,255,0.1)';

    const nameCond = prof.name_condition || { match_type: 'exists', pattern: '' };
    const descCond = prof.desc_condition || { match_type: 'none', pattern: '' };

    const nameCondText = nameCond.match_type === 'exists'
      ? '<span style="color:var(--text-secondary);">모든 인터페이스명 (전체 대표)</span>'
      : `<code>${escapeHtml(nameCond.match_type)}: ${escapeHtml(nameCond.pattern)}</code>`;

    const descCondText = descCond.match_type === 'none'
      ? '<span class="text-muted">설정 조건 없음 (Any)</span>'
      : `<span style="color:var(--accent); font-weight:600;">[${escapeHtml(descCond.match_type)}]</span> <code>${escapeHtml(descCond.pattern)}</code>`;

    const rules = prof.rules || [];
    const reqCount = rules.filter(r => r.weight !== 'optional').length;
    const optCount = rules.length - reqCount;

    const rulesPills = rules.map(r => {
      const isReq = r.weight !== 'optional';
      return `
        <div style="display:inline-flex; align-items:center; gap:6px; padding:3px 8px; border-radius:4px; font-size:11px; font-family:'Fira Code', monospace; background:${isReq ? 'rgba(88,166,255,0.08)' : 'rgba(255,255,255,0.04)'}; border:1px solid ${isReq ? 'rgba(88,166,255,0.25)' : 'var(--border)'};">
          <span style="color:${isReq ? '#e6edf3' : 'var(--text-muted)'};">${escapeHtml(r.command)}</span>
          <span style="font-size:9px; color:${isReq ? '#58a6ff' : 'var(--text-muted)'}; background:rgba(0,0,0,0.3); padding:1px 4px; border-radius:3px;">${r.match_type || 'exact'}</span>
        </div>
      `;
    }).join('');

    return `
      <div class="card" style="padding:14px 16px; background:var(--bg-secondary); border:1px solid var(--border); border-radius:8px;">
        <div class="flex justify-between items-start flex-wrap gap-2 mb-2">
          <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
            <strong style="font-size:14px; color:var(--text-primary);">${escapeHtml(prof.name)}</strong>
            <span style="font-size:11px; padding:2px 8px; border-radius:12px; font-weight:600; color:${typeColor}; background:${typeBg}; border:1px solid ${typeColor}40;">${typeLabel}</span>
            <span style="font-size:11px; color:var(--text-muted);">총 ${rules.length}개 룰 (필수 ${reqCount}, 선택 ${optCount})</span>
          </div>
          <div class="flex gap-1">
            <button class="btn btn-secondary btn-sm" onclick="window.openProfileModal('${prof.id}')" title="수정" style="padding:3px 8px; font-size:11px;">✏️ 수정</button>
            <button class="btn btn-danger btn-sm" onclick="window.deleteInterfaceProfile('${prof.id}')" title="삭제" style="padding:3px 8px; font-size:11px;">🗑️ 삭제</button>
          </div>
        </div>

        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:10px; margin-bottom:10px; font-size:12px; background:var(--bg-primary); padding:8px 12px; border-radius:6px; border:1px solid rgba(255,255,255,0.04);">
          <div>
            <span class="text-muted" style="margin-right:6px;">🔗 포트 이름:</span>
            ${nameCondText}
          </div>
          <div>
            <span class="text-muted" style="margin-right:6px;">📝 Description:</span>
            ${descCondText}
          </div>
        </div>

        <div style="display:flex; flex-wrap:wrap; gap:6px; align-items:center;">
          <span style="font-size:11px; color:var(--text-muted); font-weight:600; margin-right:4px;">필수/검사 명령어:</span>
          ${rulesPills.length > 0 ? rulesPills : '<span class="text-muted" style="font-size:11px;">(지정된 룰 없음)</span>'}
        </div>
      </div>
    `;
  }).join('');
};

window.openProfileModal = (profId = null) => {
  const modal = document.getElementById('profile-edit-modal');
  if (!modal) return;

  const idInput = document.getElementById('prof-edit-id');
  const titleEl = document.getElementById('profile-modal-title');
  const nameInput = document.getElementById('prof-name');
  const typeSelect = document.getElementById('prof-target-type');
  const nameMtypeSelect = document.getElementById('prof-name-mtype');
  const namePatternInput = document.getElementById('prof-name-pattern');
  const descMtypeSelect = document.getElementById('prof-desc-mtype');
  const descPatternInput = document.getElementById('prof-desc-pattern');

  if (profId) {
    const prof = (window._currentInterfaceProfiles || []).find(p => p.id === profId);
    if (!prof) return;
    idInput.value = prof.id;
    if (titleEl) titleEl.innerHTML = `<span>🏷️</span><span>인터페이스 정책 프로파일 수정: ${escapeHtml(prof.name)}</span>`;
    nameInput.value = prof.name || '';
    typeSelect.value = prof.target_type || 'l2';
    
    const nc = prof.name_condition || { match_type: 'exists', pattern: '' };
    nameMtypeSelect.value = nc.match_type || 'exists';
    namePatternInput.value = nc.pattern || '';

    const dc = prof.desc_condition || { match_type: 'none', pattern: '' };
    descMtypeSelect.value = dc.match_type || 'none';
    descPatternInput.value = dc.pattern || '';

    window._modalCurrentRules = Array.isArray(prof.rules) ? JSON.parse(JSON.stringify(prof.rules)) : [];
  } else {
    idInput.value = '';
    if (titleEl) titleEl.innerHTML = `<span>🏷️</span><span>새 인터페이스 정책 프로파일 추가</span>`;
    nameInput.value = '';
    typeSelect.value = 'l2';
    nameMtypeSelect.value = 'exists';
    namePatternInput.value = '';
    descMtypeSelect.value = 'contains';
    descPatternInput.value = '';
    window._modalCurrentRules = [];
  }

  window.toggleProfNamePattern();
  window.toggleProfDescPattern();
  window.renderModalRulesTable();

  modal.style.display = 'flex';
};

window.closeProfileModal = () => {
  const modal = document.getElementById('profile-edit-modal');
  if (modal) modal.style.display = 'none';
};

window.toggleProfNamePattern = () => {
  const mtype = document.getElementById('prof-name-mtype')?.value;
  const input = document.getElementById('prof-name-pattern');
  if (input) {
    if (mtype === 'exists') {
      input.disabled = true;
      input.placeholder = '모든 인터페이스명 허용 (와일드카드)';
    } else {
      input.disabled = false;
      input.placeholder = '포트명 패턴 (예: ^(Gigabit|TenGigabit)Ethernet1/0/(2[3-4])$)';
    }
  }
};

window.toggleProfDescPattern = () => {
  const mtype = document.getElementById('prof-desc-mtype')?.value;
  const input = document.getElementById('prof-desc-pattern');
  if (input) {
    if (mtype === 'none') {
      input.disabled = true;
      input.placeholder = 'Description 조건 없이 매칭';
    } else {
      input.disabled = false;
      input.placeholder = 'Description 키워드/정규식 (예: UPLINK, TO-CORE, SERVER, AP)';
    }
  }
};

window.renderModalRulesTable = () => {
  const tbody = document.getElementById('prof-rules-tbody');
  const badge = document.getElementById('prof-rules-count-badge');
  if (!tbody) return;

  const rules = window._modalCurrentRules || [];
  if (badge) badge.textContent = `${rules.length}개 룰`;

  if (rules.length === 0) {
    tbody.innerHTML = `<tr><td colspan="4" class="text-muted text-center" style="padding:10px;">아직 등록된 룰이 없습니다. 위에서 명령어를 추가하세요.</td></tr>`;
    return;
  }

  tbody.innerHTML = rules.map((r, idx) => {
    return `
      <tr>
        <td style="font-family:'Fira Code', monospace; color:#e6edf3;">${escapeHtml(r.command)}</td>
        <td><span class="guide-badge badge-${r.match_type || 'exact'}" style="font-size:10px;">${r.match_type || 'exact'}</span></td>
        <td><span style="font-size:11px; color:${r.weight === 'optional' ? 'var(--text-muted)' : 'var(--accent)'}; font-weight:600;">${r.weight === 'optional' ? '선택' : '필수'}</span></td>
        <td style="text-align:center;">
          <button class="btn btn-sm btn-danger" style="padding:2px 6px; font-size:11px;" onclick="window.deleteRuleFromModal(${idx})">🗑️</button>
        </td>
      </tr>
    `;
  }).join('');
};

window.addRuleToCurrentProfile = () => {
  const cmdInput = document.getElementById('prof-new-rule-cmd');
  const mtypeSelect = document.getElementById('prof-new-rule-mtype');
  const weightSelect = document.getElementById('prof-new-rule-weight');

  const cmd = (cmdInput?.value || '').trim();
  if (!cmd) return toast('명령어를 입력하세요.', 'warning');

  const mtype = mtypeSelect?.value || 'exact';
  const weight = weightSelect?.value || 'required';

  window._modalCurrentRules.push({
    id: 'rule-' + Date.now() + Math.random().toString(36).substr(2, 4),
    command: cmd,
    match_type: mtype,
    weight: weight
  });

  cmdInput.value = '';
  window.renderModalRulesTable();
};

window.deleteRuleFromModal = (idx) => {
  if (idx >= 0 && idx < window._modalCurrentRules.length) {
    window._modalCurrentRules.splice(idx, 1);
    window.renderModalRulesTable();
  }
};

window.saveProfileFromModal = () => {
  const idInput = document.getElementById('prof-edit-id');
  const nameInput = document.getElementById('prof-name');
  const typeSelect = document.getElementById('prof-target-type');
  const nameMtypeSelect = document.getElementById('prof-name-mtype');
  const namePatternInput = document.getElementById('prof-name-pattern');
  const descMtypeSelect = document.getElementById('prof-desc-mtype');
  const descPatternInput = document.getElementById('prof-desc-pattern');

  const name = (nameInput?.value || '').trim();
  if (!name) return toast('프로파일 이름을 입력하세요.', 'warning');

  const profId = idInput?.value || ('prof-' + Date.now());
  const targetType = typeSelect?.value || 'l2';
  const nameMtype = nameMtypeSelect?.value || 'exists';
  const namePattern = (namePatternInput?.value || '').trim();
  const descMtype = descMtypeSelect?.value || 'none';
  const descPattern = (descPatternInput?.value || '').trim();

  const newProfile = {
    id: profId,
    name: name,
    target_type: targetType,
    name_condition: {
      match_type: nameMtype,
      pattern: namePattern
    },
    desc_condition: {
      match_type: descMtype,
      pattern: descPattern
    },
    rules: window._modalCurrentRules || []
  };

  const existingIdx = window._currentInterfaceProfiles.findIndex(p => p.id === profId);
  if (existingIdx >= 0) {
    window._currentInterfaceProfiles[existingIdx] = newProfile;
    toast(`인터페이스 프로파일 "${name}" 수정 완료`, 'success');
  } else {
    window._currentInterfaceProfiles.push(newProfile);
    toast(`인터페이스 프로파일 "${name}" 추가 완료`, 'success');
  }

  window.closeProfileModal();
  window.renderInterfaceProfiles();
  window.updateProfileTabBadge();
};

window.deleteInterfaceProfile = (profId) => {
  const prof = window._currentInterfaceProfiles.find(p => p.id === profId);
  if (!prof) return;
  if (!confirm(`인터페이스 정책 프로파일 "${prof.name}"을 삭제하시겠습니까?`)) return;

  window._currentInterfaceProfiles = window._currentInterfaceProfiles.filter(p => p.id !== profId);
  window.renderInterfaceProfiles();
  window.updateProfileTabBadge();
  toast('프로파일이 삭제되었습니다.', 'info');
};
