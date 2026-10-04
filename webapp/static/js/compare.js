// compare.js — 골든 템플릿별 트리 구조 설정 비교 및 결과 관리

import { api, uploadFile, initDropZone, toast, overallChip, fmtDate, setLoading } from './app.js';

function escapeHtml(s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

export function initCompare() {
  // 탭 클릭 및 초기 로드 시 골든 템플릿별 트리 로드
  const tabBtn = document.querySelector('[data-tab="tab-compare"]');
  if (tabBtn) {
    tabBtn.addEventListener('click', () => {
      loadCompareTree();
    });
  }
  loadCompareTree();

  // 트리 컨테이너 이벤트 위임 (체크박스 및 템플릿 전체 선택)
  const treeContainer = document.getElementById('compare-tree-container');
  if (treeContainer) {
    treeContainer.addEventListener('change', (e) => {
      // 1. 개별 행 체크박스
      if (e.target && e.target.classList.contains('compare-row-check')) {
        updateSelectionState();
      }
      // 2. 템플릿별 마스터 체크박스
      if (e.target && e.target.classList.contains('tpl-select-all')) {
        const tplId = e.target.dataset.templateId;
        const isChecked = e.target.checked;
        document.querySelectorAll(`.compare-row-check[data-template-id="${tplId}"]`).forEach(cb => {
          cb.checked = isChecked;
        });
        updateSelectionState();
      }
    });
  }

  // 다중 재비교 및 다중 삭제 버튼 이벤트 바인딩
  const recompareBtn = document.getElementById('compare-batch-recompare-btn');
  if (recompareBtn) {
    recompareBtn.addEventListener('click', batchRecompare);
  }

  const deleteBtn = document.getElementById('compare-batch-delete-btn');
  if (deleteBtn) {
    deleteBtn.addEventListener('click', batchDelete);
  }

  // ESC 키 누르면 드로어 닫기
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      const drawer = document.getElementById('compare-drawer');
      if (drawer && drawer.classList.contains('open')) {
        window.closeCompareResult();
      }
    }
  });
}

export async function loadCompareTree() {
  const container = document.getElementById('compare-tree-container');
  if (!container) return;

  try {
    const [templates, results] = await Promise.all([
      api('/api/golden/templates?_=' + Date.now()),
      api('/api/compare/results?_=' + Date.now()),
    ]);

    if (!templates || templates.length === 0) {
      container.innerHTML = `
        <div class="empty-state card" style="padding:48px 24px; text-align:center;">
          <div class="empty-icon" style="font-size:40px; margin-bottom:12px;">🛡️</div>
          <h3 style="font-size:16px; font-weight:700; margin-bottom:8px;">등록된 골든 템플릿이 없습니다</h3>
          <p class="text-muted text-sm" style="margin-bottom:16px;">
            설정 파일 감사를 진행하려면 먼저 기준이 되는 골든 템플릿을 생성해야 합니다.
          </p>
          <button class="btn btn-primary btn-sm" onclick="document.querySelector('[data-tab=\\'tab-golden\\']').click()">
            ⚡ 골든 템플릿 생성하러 가기
          </button>
        </div>
      `;
      updateSelectionState();
      return;
    }

    // 결과를 템플릿 ID별로 그룹핑
    const resultsByTpl = {};
    templates.forEach(t => { resultsByTpl[t.id] = []; });
    const orphanResults = [];

    if (results && results.length > 0) {
      if (!window._compareResults) window._compareResults = {};
      results.forEach(r => {
        window._compareResults[r.id] = r;
        if (r.template_id && resultsByTpl[r.template_id]) {
          resultsByTpl[r.template_id].push(r);
        } else {
          orphanResults.push(r);
        }
      });
    }

    // 템플릿별 트리 노드 HTML 생성
    container.innerHTML = templates.map(t => {
      const items = resultsByTpl[t.id] || [];
      const osName = (t.os || 'iosxe').toUpperCase();

      return `
        <div class="compare-tpl-node" id="tpl-node-${t.id}" data-template-id="${t.id}">
          <!-- 1. 골든 템플릿 헤더 (상위 노드) -->
          <div class="compare-tpl-header">
            <div class="flex items-center gap-2 flex-wrap">
              <span style="font-size:20px;">🛡️</span>
              <span style="font-weight:700; font-size:15px; color:var(--text-primary);">${escapeHtml(t.name)}</span>
              <span class="guide-badge badge-exact" style="font-size:11px; padding:2px 8px;">${osName}</span>
              <span style="font-size:12px; color:var(--text-muted); background:var(--bg-secondary); padding:2px 8px; border-radius:4px;">
                기준 템플릿
              </span>
              ${t.description ? `<span style="font-size:12px; color:var(--text-muted); margin-left:4px;">· ${escapeHtml(t.description)}</span>` : ''}
            </div>
            <div class="flex items-center gap-3">
              <span class="text-xs text-muted">
                비교 파일: <strong id="tpl-count-${t.id}" style="color:var(--accent);">${items.length}</strong>건
              </span>
            </div>
          </div>

          ${t.has_pending_change ? `
            <div class="compare-tpl-pending-ribbon" onclick="event.stopPropagation(); window.openTemplateImpactModal('${t.id}')">
              <div class="flex items-center gap-2">
                <span class="impact-pulse-icon">⚠️</span>
                <strong style="color:var(--review);">골든 템플릿 규칙 변경 감지</strong>
                <span class="text-xs text-muted">— 연동 장비 ${t.change_summary?.affected_count || items.length}대에 대한 재감사 허용 또는 롤백 대기 중</span>
              </div>
              <button class="btn btn-warning btn-xs flex items-center gap-1" style="margin-left:auto; font-size:11px; padding:3px 8px;">
                <span>영향 분석 및 결정</span><span>▶</span>
              </button>
            </div>
          ` : ''}

          <!-- 2. 트리 하위 브랜치 (들여쓰기 구조) -->
          <div class="compare-tree-branch">
            
            <!-- 이 템플릿 전용 실시간 파일 업로드 / 드롭존 -->
            <div class="compare-mini-dropzone" id="drop-zone-${t.id}" data-template-id="${t.id}" title="클릭하거나 파일을 드래그하여 ${escapeHtml(t.name)}와 실시간 비교">
              <input type="file" id="file-input-${t.id}" data-template-id="${t.id}" data-os="${t.os || 'iosxe'}" accept=".cfg,.txt,.conf,.log" multiple style="display:none;">
              <div class="flex items-center gap-3">
                <span style="font-size:22px;">📥</span>
                <div>
                  <div style="font-size:13px; font-weight:600; color:var(--text-primary);">
                    <span style="color:var(--accent);">${escapeHtml(t.name)}</span>와 실시간 비교할 장비 설정 파일 드래그 또는 추가
                  </div>
                  <div style="font-size:11px; color:var(--text-muted); margin-top:2px;">
                    여러 파일을 한 번에 올릴 수 있으며, 완료 시 들여쓰기된 트리 하위 항목으로 즉시 등록됩니다.
                  </div>
                </div>
              </div>
              <button class="btn btn-secondary btn-sm flex items-center gap-1" onclick="event.stopPropagation(); document.getElementById('file-input-${t.id}').click();">
                <span>➕</span> 파일 선택
              </button>
            </div>

            <!-- 트리 하위 비교 결과 테이블 -->
            <div class="compare-tree-table-wrapper">
              <table class="data-table table-hoverable compare-tree-table">
                <colgroup>
                  <col class="col-check" style="width:36px;">
                  <col class="col-filename">
                  <col class="col-hostname" style="width:150px;">
                  <col class="col-time" style="width:135px;">
                  <col class="col-score" style="width:75px;">
                  <col class="col-action" style="width:180px;">
                </colgroup>
                <thead>
                  <tr>
                    <th class="col-check" style="text-align:center;">
                      <input type="checkbox" class="tpl-select-all" data-template-id="${t.id}" title="이 템플릿의 전체 항목 선택">
                    </th>
                    <th class="col-filename">업로드 파일</th>
                    <th class="col-hostname">HOSTNAME</th>
                    <th class="col-time">검사 시간</th>
                    <th class="col-score">점수</th>
                    <th class="col-action" style="text-align:right;">액션</th>
                  </tr>
                </thead>
                <tbody id="tpl-tbody-${t.id}">
                  ${items.length === 0 ? `
                    <tr class="empty-row"><td colspan="6" class="empty-state" style="padding:14px; font-size:12px; color:var(--text-muted);">아직 비교된 설정 파일이 없습니다. 위 업로드 영역에 파일을 추가하여 감사를 실행하세요.</td></tr>
                  ` : items.map(r => renderRowHtml(r, t.id)).join('')}
                </tbody>
              </table>
            </div>

          </div>
        </div>
      `;
    }).join('');

    // 각 템플릿의 미니 드롭존 이벤트 바인딩
    templates.forEach(t => {
      const zone = document.getElementById(`drop-zone-${t.id}`);
      const input = document.getElementById(`file-input-${t.id}`);
      if (zone && input) {
        initDropZone(zone, input, async (files) => {
          if (!files || files.length === 0) return;
          toast(`[${t.name}] ${files.length}개 파일 실시간 비교를 시작합니다...`, 'info');
          let lastResult = null;
          for (let i = 0; i < files.length; i++) {
            const res = await processSingleFile(files[i], t.id, t.name, t.os);
            if (res) lastResult = res;
          }
          if (lastResult) {
            toast(`비교 완료! 점수: ${lastResult.score}% (${lastResult.overall.toUpperCase()}) - 결과 목록에서 상세 보기를 누르세요.`, 'success');
          }
        });
      }
    });

    updateSelectionState();
    if (window.checkPendingTemplateChanges) {
      window.checkPendingTemplateChanges();
    }
  } catch (err) {
    console.error('loadCompareTree error:', err);
    container.innerHTML = `<div class="empty-state" style="color:var(--danger)">비교 목록 로드 실패: ${err.message}</div>`;
  }
}

function renderRowHtml(r, templateId) {
  const displayName = r.filename || r.hostname;
  return `
    <tr id="row-${r.id}">
      <td class="col-check" style="text-align:center;">
        <input type="checkbox" class="compare-row-check" data-id="${r.id}" data-template-id="${templateId}">
      </td>
      <td class="col-filename">
        <div class="compare-file-wrap">
          <span style="color:var(--accent); font-size:13px; flex-shrink:0;">📄</span>
          <strong class="compare-filename" title="${escapeHtml(displayName)}">${escapeHtml(displayName)}</strong>
        </div>
      </td>
      <td class="col-hostname">
        <div class="compare-hostname-cell">
          ${(r.hostname) ? `<code class="compare-hostname-code" title="${escapeHtml(r.hostname)}">${escapeHtml(r.hostname)}</code>` : '<span class="text-muted" style="font-size:11px;">—</span>'}
        </div>
      </td>
      <td class="col-time"><div style="font-size:12px; color:var(--text-muted); white-space:nowrap;">${new Date(r.created_at).toLocaleString('ko-KR', {dateStyle:'short',timeStyle:'short'})}</div></td>
      <td class="col-score"><strong>${r.score}%</strong></td>
      <td class="col-action" style="text-align:right;">
        <div class="compare-action-btns">
          <button class="btn btn-sm btn-secondary compare-view-btn" onclick="window.viewResult('${r.id}')">
            <span style="font-size:12px;">🔍</span><span>상세 보기</span>
          </button>
          <button class="btn btn-sm btn-danger compare-delete-btn" onclick="window.deleteCompareItem('row-${r.id}', '${r.id}')" title="결과 삭제">
            <span style="font-size:12px;">🗑️</span><span>삭제</span>
          </button>
        </div>
      </td>
    </tr>
  `;
}

async function processSingleFile(file, templateId, templateName, osType) {
  const tbody = document.getElementById(`tpl-tbody-${templateId}`);
  if (!tbody) return null;

  const emptyRow = tbody.querySelector('.empty-row');
  if (emptyRow) emptyRow.remove();

  const tr = document.createElement('tr');
  const tempRowId = 'row-temp-' + Date.now() + Math.random().toString(36).substr(2, 5);
  tr.id = tempRowId;

  tr.innerHTML = `
    <td class="col-check" style="text-align:center;"><input type="checkbox" disabled></td>
    <td class="col-filename">
      <div class="compare-file-wrap">
        <span style="color:var(--accent); font-size:13px; flex-shrink:0;">📄</span>
        <strong class="compare-filename" title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</strong>
      </div>
    </td>
    <td class="col-hostname"><span class="text-muted" style="font-size:11px;">분석 중...</span></td>
    <td class="col-time"><div class="spinner" style="width:14px;height:14px;display:inline-block"></div> 1/2 파싱 중...</td>
    <td class="col-score">-</td>
    <td class="col-action">-</td>
  `;
  tbody.insertBefore(tr, tbody.firstChild);

  try {
    // 1. Upload & Parsing
    const data = await uploadFile(`/api/compare/upload?os=${osType || 'iosxe'}`, file);
    const hostname = data.hostname || file.name;

    const timeCell = tr.querySelector('.col-time');
    if (timeCell) {
      timeCell.innerHTML = `<div class="spinner" style="width:14px;height:14px;display:inline-block"></div> 2/2 골든 템플릿과 비교 중...`;
    }

    // 2. Run compare (서버가 같은 템플릿 내 중복 파일명을 감지하여 (2), (3) 등으로 자동 넘버링)
    const result = await api('/api/compare/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ parsed: data.parsed, template_id: templateId, save: true, filename: file.name }),
    });

    const finalRowId = 'row-' + result.id;
    tr.id = finalRowId;

    const finalFilename = result.filename || file.name;
    const finalHostname = hostname || result.hostname;

    tr.innerHTML = `
      <td class="col-check" style="text-align:center;">
        <input type="checkbox" class="compare-row-check" data-id="${result.id}" data-template-id="${templateId}">
      </td>
      <td class="col-filename">
        <div class="compare-file-wrap">
          <span style="color:var(--accent); font-size:13px; flex-shrink:0;">📄</span>
          <strong class="compare-filename" title="${escapeHtml(finalFilename)}">${escapeHtml(finalFilename)}</strong>
        </div>
      </td>
      <td class="col-hostname">
        <div class="compare-hostname-cell">
          ${(finalHostname) ? `<code class="compare-hostname-code" title="${escapeHtml(finalHostname)}">${escapeHtml(finalHostname)}</code>` : '<span class="text-muted" style="font-size:11px;">—</span>'}
        </div>
      </td>
      <td class="col-time"><div style="font-size:12px; color:var(--text-muted); white-space:nowrap;">${new Date().toLocaleTimeString('ko-KR')}</div></td>
      <td class="col-score"><strong>${result.score}%</strong></td>
      <td class="col-action" style="text-align:right;">
        <div class="compare-action-btns">
          <button class="btn btn-sm btn-secondary compare-view-btn" onclick="window.viewResult('${result.id}')">
            <span style="font-size:12px;">🔍</span><span>상세 보기</span>
          </button>
          <button class="btn btn-sm btn-danger compare-delete-btn" onclick="window.deleteCompareItem('${finalRowId}', '${result.id}')" title="결과 삭제">
            <span style="font-size:12px;">🗑️</span><span>삭제</span>
          </button>
        </div>
      </td>
    `;

    if (!window._compareResults) window._compareResults = {};
    window._compareResults[result.id] = { ...result, filename: finalFilename };

    updateTemplateCount(templateId);
    updateSelectionState();
    return result;
  } catch (err) {
    const timeCell = tr.querySelector('.col-time');
    if (timeCell) timeCell.innerHTML = `<span style="color:var(--danger)">❌ 오류: ${escapeHtml(err.message)}</span>`;
    return null;
  }
}

function updateTemplateCount(templateId) {
  const tbody = document.getElementById(`tpl-tbody-${templateId}`);
  const countSpan = document.getElementById(`tpl-count-${templateId}`);
  if (tbody && countSpan) {
    const validRows = tbody.querySelectorAll('tr:not(.empty-row)');
    countSpan.textContent = validRows.length;
  }
}

function updateSelectionState() {
  const allChecks = Array.from(document.querySelectorAll('.compare-row-check'));
  const checked = allChecks.filter(cb => cb.checked);
  const count = checked.length;

  const countSpan = document.getElementById('compare-selected-count');
  if (countSpan) countSpan.textContent = count;

  const recompareBtn = document.getElementById('compare-batch-recompare-btn');
  const deleteBtn = document.getElementById('compare-batch-delete-btn');
  if (recompareBtn) recompareBtn.disabled = count === 0;
  if (deleteBtn) deleteBtn.disabled = count === 0;

  // 템플릿별 마스터 체크박스 상태 갱신
  document.querySelectorAll('.tpl-select-all').forEach(masterCb => {
    const tplId = masterCb.dataset.templateId;
    const tplRowChecks = Array.from(document.querySelectorAll(`.compare-row-check[data-template-id="${tplId}"]`));
    const tplChecked = tplRowChecks.filter(cb => cb.checked);
    if (tplRowChecks.length === 0) {
      masterCb.checked = false;
      masterCb.indeterminate = false;
    } else if (tplChecked.length === tplRowChecks.length) {
      masterCb.checked = true;
      masterCb.indeterminate = false;
    } else if (tplChecked.length > 0) {
      masterCb.checked = false;
      masterCb.indeterminate = true;
    } else {
      masterCb.checked = false;
      masterCb.indeterminate = false;
    }
  });
}

async function batchRecompare() {
  const checkedBoxes = Array.from(document.querySelectorAll('.compare-row-check:checked'));
  const ids = checkedBoxes.map(cb => cb.dataset.id).filter(Boolean);
  if (ids.length === 0) {
    toast('다시 비교할 항목을 선택해주세요.', 'info');
    return;
  }

  const recompareBtn = document.getElementById('compare-batch-recompare-btn');
  if (recompareBtn) {
    recompareBtn.disabled = true;
    recompareBtn.textContent = '🔄 비교 중...';
  }

  try {
    toast(`${ids.length}개 항목 재비교를 시작합니다...`, 'info');
    const res = await api('/api/compare/recompare', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ result_ids: ids })
    });

    if (res.updated) {
      for (const item of res.updated) {
        const tr = document.getElementById(`row-${item.id}`);
        if (tr) {
          const timeCell = tr.querySelector('.col-time');
          const scoreCell = tr.querySelector('.col-score');
          if (timeCell) timeCell.innerHTML = `<div style="font-size:12px; color:var(--text-muted)">재비교 (${new Date().toLocaleTimeString('ko-KR')})</div>`;
          if (scoreCell) scoreCell.innerHTML = `<strong>${item.score}%</strong>`;
        }
        if (!window._compareResults) window._compareResults = {};
        window._compareResults[item.id] = { ...item.detail, id: item.id, hostname: item.hostname, filename: item.filename || item.hostname, template_name: item.template_name, score: item.score, overall: item.overall };
        
        // 상세 영역이 현재 이 항목을 보고 있으면 새로고침
        const area = document.getElementById('compare-result-area');
        if (area && area.dataset.resultId === item.id) {
          renderResult(window._compareResults[item.id]);
        }
      }
      toast(`${res.updated.length}개 항목 재비교가 완료되었습니다.`, 'success');
    }
  } catch (err) {
    toast(`재비교 실패: ${err.message}`, 'error');
  } finally {
    if (recompareBtn) {
      recompareBtn.disabled = false;
      recompareBtn.innerHTML = `🔄 선택 항목 다시 비교 (<span id="compare-selected-count">0</span>)`;
    }
    updateSelectionState();
  }
}

async function batchDelete() {
  const checkedBoxes = Array.from(document.querySelectorAll('.compare-row-check:checked'));
  const ids = checkedBoxes.map(cb => cb.dataset.id).filter(Boolean);
  if (ids.length === 0) {
    toast('삭제할 항목을 선택해주세요.', 'info');
    return;
  }

  if (!confirm(`선택한 ${ids.length}개 비교 결과를 삭제하시겠습니까?`)) return;

  const deleteBtn = document.getElementById('compare-batch-delete-btn');
  if (deleteBtn) {
    deleteBtn.disabled = true;
    deleteBtn.textContent = '🗑️ 삭제 중...';
  }

  try {
    await api('/api/compare/delete_batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ result_ids: ids })
    });

    const affectedTplIds = new Set();
    for (const id of ids) {
      const tr = document.getElementById(`row-${id}`);
      if (tr) {
        const tplId = tr.querySelector('.compare-row-check')?.dataset.templateId;
        if (tplId) affectedTplIds.add(tplId);
        const tbody = tr.closest('tbody');
        tr.remove();
        if (tbody && tbody.children.length === 0) {
          tbody.innerHTML = '<tr class="empty-row"><td colspan="7" class="empty-state" style="padding:14px; font-size:12px; color:var(--text-muted);">아직 비교된 설정 파일이 없습니다. 위 업로드 영역에 파일을 추가하여 감사를 실행하세요.</td></tr>';
        }
      }
      if (window._compareResults && window._compareResults[id]) {
        delete window._compareResults[id];
      }
      const currentDetail = document.getElementById('compare-result-area');
      if (currentDetail && currentDetail.dataset.resultId === id) {
        window.closeCompareResult();
      }
    }

    affectedTplIds.forEach(tplId => updateTemplateCount(tplId));
    toast(`${ids.length}개 결과가 삭제되었습니다.`, 'info');
  } catch (err) {
    toast(`일괄 삭제 실패: ${err.message}`, 'error');
  } finally {
    if (deleteBtn) {
      deleteBtn.disabled = false;
      deleteBtn.textContent = '🗑️ 선택 항목 삭제';
    }
    updateSelectionState();
  }
}

window.deleteCompareItem = async (rowId, resultId) => {
  if (!confirm('이 비교 결과를 삭제하시겠습니까?')) return;
  try {
    if (resultId) {
      await api(`/api/compare/results/${resultId}`, { method: 'DELETE' });
      if (window._compareResults && window._compareResults[resultId]) {
        delete window._compareResults[resultId];
      }
    }
    const tr = document.getElementById(rowId);
    if (tr) {
      const tbody = tr.closest('tbody');
      const tplId = tr.querySelector('.compare-row-check')?.dataset.templateId;
      tr.style.opacity = '0';
      tr.style.transition = 'opacity 0.2s';
      setTimeout(() => {
        tr.remove();
        if (tbody && tbody.children.length === 0) {
          tbody.innerHTML = '<tr class="empty-row"><td colspan="7" class="empty-state" style="padding:14px; font-size:12px; color:var(--text-muted);">아직 비교된 설정 파일이 없습니다. 위 업로드 영역에 파일을 추가하여 감사를 실행하세요.</td></tr>';
        }
        if (tplId) updateTemplateCount(tplId);
        updateSelectionState();
      }, 200);
    }
    const currentDetail = document.getElementById('compare-result-area');
    if (currentDetail && currentDetail.dataset.resultId === resultId) {
      window.closeCompareResult();
    }
    toast('비교 결과가 삭제되었습니다.', 'info');
  } catch (err) {
    toast(`삭제 실패: ${err.message}`, 'error');
  }
};

window.viewResult = async (id) => {
  try {
    // 활성 행 하이라이트 전환
    document.querySelectorAll('.compare-tpl-node tr.row-active-detail').forEach(tr => tr.classList.remove('row-active-detail'));
    const targetTr = document.getElementById('row-' + id);
    if (targetTr) {
      targetTr.classList.add('row-active-detail');
    }

    let result = window._compareResults && window._compareResults[id];
    if (!result || !result.items) {
      const r = await api(`/api/compare/results/${id}`);
      result = { ...r.detail, id: r.id, hostname: r.hostname, filename: r.filename || r.detail?.filename || r.hostname, template_name: r.template_name };
      if (!window._compareResults) window._compareResults = {};
      window._compareResults[id] = result;
    }
    renderResult(result);

    // 슬라이드 드로어 열기 (화면 강제 점프 없음)
    const drawer = document.getElementById('compare-drawer');
    const backdrop = document.getElementById('compare-drawer-backdrop');
    if (drawer) {
      drawer.classList.add('open');
      drawer.setAttribute('aria-hidden', 'false');
    }
    if (backdrop) {
      backdrop.classList.add('open');
    }
    const drawerBody = document.querySelector('.compare-drawer-body');
    if (drawerBody) {
      drawerBody.scrollTop = 0;
    }
  } catch (err) {
    toast(`결과 조회 실패: ${err.message}`, 'error');
  }
};

window.closeCompareResult = () => {
  const drawer = document.getElementById('compare-drawer');
  const backdrop = document.getElementById('compare-drawer-backdrop');
  if (drawer) {
    drawer.classList.remove('open');
    drawer.setAttribute('aria-hidden', 'true');
  }
  if (backdrop) {
    backdrop.classList.remove('open');
  }
  const area = document.getElementById('compare-result-area');
  if (area) {
    delete area.dataset.resultId;
  }
  document.querySelectorAll('.compare-tpl-node tr.row-active-detail').forEach(tr => tr.classList.remove('row-active-detail'));
};

// ── Extra Config & Rollback Window Handlers ──
window.switchResultTab = (tabName) => {
  document.querySelectorAll('.result-tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tabName);
  });
  document.querySelectorAll('.result-tab-content').forEach(panel => {
    panel.style.display = panel.id === `tab-content-${tabName}` ? 'block' : 'none';
  });
};

window.copyRollbackCmd = (btn, cmd) => {
  navigator.clipboard.writeText(cmd).then(() => {
    const orig = btn.innerHTML;
    btn.innerHTML = '<span>✅ 복사됨!</span>';
    btn.style.borderColor = 'var(--pass)';
    btn.style.color = 'var(--pass)';
    setTimeout(() => {
      btn.innerHTML = orig;
      btn.style.borderColor = '';
      btn.style.color = '';
    }, 1500);
  });
};

window.copyFullRollbackScript = (btn) => {
  const pre = document.getElementById('rollback-script-content');
  if (!pre) return;
  const scriptText = pre.textContent;
  navigator.clipboard.writeText(scriptText).then(() => {
    const orig = btn.innerHTML;
    btn.innerHTML = '<span>✅ 복사 완료!</span>';
    setTimeout(() => {
      btn.innerHTML = orig;
    }, 1800);
    toast('전체 롤백 CLI 스크립트가 클립보드에 복사되었습니다.', 'success');
  });
};

window.downloadResultRollback = (resultId) => {
  if (!resultId) return;
  window.open(`/api/compare/results/${resultId}/rollback`, '_blank');
};

window.downloadResultCleanConfig = (resultId) => {
  if (!resultId) return;
  window.open(`/api/compare/results/${resultId}/clean_config`, '_blank');
};

export function renderResult(result, containerId = 'compare-result-area') {
  const area = document.getElementById(containerId);
  if (!area) return;

  const resultId = result.id || '';
  area.dataset.resultId = resultId;

  const overall = result.overall || 'pass';
  const statusIcons = { pass: '✅', review: '⚠️', fail: '❌' };
  const displayName = result.filename || result.hostname || '결과 상세';
  const stickyTop = '0px';

  const extraConfigs = Array.isArray(result.extra_configs) ? result.extra_configs : [];
  const extraCount = extraConfigs.length;
  const extraSummary = result.extra_summary || {
    total: extraCount,
    danger: extraConfigs.filter(e => e.risk === 'danger').length,
    warning: extraConfigs.filter(e => e.risk === 'warning').length,
    info: extraConfigs.filter(e => e.risk === 'info').length,
  };
  const rollbackScript = result.rollback_script || '! No rollback script available.';

  // 드로어 상단 고정 헤더 엘리먼트 갱신
  if (containerId === 'compare-result-area') {
    const badgeEl = document.getElementById('drawer-badge');
    const filenameEl = document.getElementById('drawer-filename');
    const metaEl = document.getElementById('drawer-meta');
    const scoreEl = document.getElementById('drawer-score');
    const scoreBarEl = document.getElementById('drawer-score-bar');

    if (badgeEl) {
      badgeEl.className = `drawer-badge ${overall}`;
      badgeEl.textContent = overall.toUpperCase();
    }
    if (filenameEl) {
      filenameEl.textContent = displayName;
    }
    if (metaEl) {
      const hostExtra = (result.hostname && displayName !== result.hostname) ? ` · Hostname: ${result.hostname}` : '';
      const extraNotice = extraCount > 0 
        ? ` · <span style="color:${extraSummary.danger > 0 ? '#f85149' : '#ffa657'}; font-weight:700;">⚠️ 미인가/추가 설정 ${extraCount}건 감지</span>`
        : ` · <span style="color:var(--pass);">✓ 추가 설정 없음 (Clean)</span>`;
      metaEl.innerHTML = `템플릿: <strong>${escapeHtml(result.template_name || '')}</strong> · 통과 ${result.passed_items || 0}/${result.total_items || 0} 항목${hostExtra}${extraNotice}`;
    }
    if (scoreEl) {
      scoreEl.textContent = `${result.score ?? 0}%`;
    }
    if (scoreBarEl) {
      scoreBarEl.className = `score-fill ${overall}`;
      scoreBarEl.style.width = `${result.score ?? 0}%`;
    }
  }

  // 1. 골든 룰 섹션별 그룹핑
  const grouped = {};
  const rawItems = Array.isArray(result.items) ? result.items : [];
  rawItems.forEach(item => {
    let sec = item.section || '기타 설정';
    if (sec.startsWith('interface')) {
      if (item.id.includes('.uplink.') || item.id.includes('.L2.')) {
        // 인터페이스 약어 유지
      } else {
        sec = 'INTERFACE (PARSED)';
      }
    }
    if (!grouped[sec]) grouped[sec] = [];
    grouped[sec].push(item);
  });

  const sectionHtmls = Object.keys(grouped).sort().map(sec => {
    const items = grouped[sec];
    const isUplink = sec.startsWith('interface (uplink)') || sec.includes('GigabitEthernet') || sec.includes('TenGigabit');
    const isL2 = sec.includes('(L2)');
    const sectionIcon = isUplink ? '🔗' : isL2 ? '🔀' : '📂';

    const itemsHtml = items.map(item => {
      let cleanLabel = item.label;
      if (sec.toLowerCase().includes('interface') && cleanLabel.includes(' → ')) {
        cleanLabel = cleanLabel.split(' → ').pop();
      }

      const mtype = item.match_type || 'exact';
      const matchBadgeClass = `guide-badge badge-${mtype}`;

      return `
        <div class="result-item ${item.status}">
          <span class="result-item-icon">${statusIcons[item.status] || '?'}</span>
          <div style="flex:1; min-width:0;">
            <div class="result-item-label" style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
              <span>${escapeHtml(cleanLabel)}</span>
              <span class="guide-badge ${matchBadgeClass}" style="font-size:10px; padding:1px 6px;">${mtype}</span>
              ${item.weight === 'optional' ? '<span style="font-size:10px; color:var(--text-muted); background:var(--bg-primary); padding:1px 4px; border-radius:3px;">optional</span>' : ''}
            </div>
            <div class="result-item-msg" style="margin-top:3px; font-size:11px;">
              ${item.status === 'pass'
                ? `<span style="color:var(--success);">확인됨:</span> <code>${escapeHtml(item.actual)}</code>`
                : `<span style="color:var(--danger); font-weight:600;">불일치:</span> 기대 <code>${escapeHtml(item.expected)}</code> / 실제 <code>${escapeHtml(item.actual || '(없음)')}</code> <span style="color:var(--text-muted);">(${escapeHtml(item.message)})</span>`}
            </div>
          </div>
          <span class="result-item-status ${item.status}">${item.status.toUpperCase()}</span>
        </div>
      `;
    }).join('');

    const firstProfName = items.find(i => i.profile_name)?.profile_name;
    const profBadge = firstProfName ? `<span style="font-size:11px; padding:1px 8px; border-radius:10px; background:rgba(88,166,255,0.12); color:#58a6ff; border:1px solid rgba(88,166,255,0.3); font-weight:600; margin-left:6px;">🏷️ ${escapeHtml(firstProfName)}</span>` : '';

    return `
      <div class="section-group" style="margin-bottom: 20px;">
        <div class="section-group-header" style="background:var(--bg-secondary); padding:8px 12px; margin-bottom:8px; border-radius:6px; font-weight:bold; color:var(--accent); font-size:13px; display:flex; align-items:center; gap:8px; border-left: 3px solid var(--accent); position: sticky; top: ${stickyTop}; z-index: 5;">
          <span style="font-size:16px;">${sectionIcon}</span> 
          <span>${sec.toUpperCase()} <span style="color:var(--text-muted); font-size:11px; font-weight:normal;">(${items.length}개 항목)</span></span>
          ${profBadge}
        </div>
        <div class="result-items" style="display: flex; flex-direction: column; gap: 6px;">
          ${itemsHtml}
        </div>
      </div>
    `;
  }).join('');

  // 2. 추가된 설정(Extra Configs) HTML 생성
  let extraHtml = '';
  if (extraCount === 0) {
    extraHtml = `
      <div class="card" style="padding:32px 20px; text-align:center; background:rgba(63,185,80,0.05); border:1px solid rgba(63,185,80,0.2);">
        <div style="font-size:32px; margin-bottom:10px;">🛡️</div>
        <h4 style="font-size:15px; font-weight:700; color:var(--pass); margin-bottom:6px;">추가된 미인가 설정 없음 (Clean Config)</h4>
        <p class="text-muted text-xs">비교 대상 장비에 골든 템플릿 외의 불필요하거나 보안을 해치는 추가 명령어가 없습니다.</p>
      </div>
    `;
  } else {
    const extraCards = extraConfigs.map(ec => {
      const riskLevel = ec.risk || 'info';
      const riskIcon = riskLevel === 'danger' ? '🚨' : riskLevel === 'warning' ? '⚠️' : 'ℹ️';
      const riskLabel = riskLevel === 'danger' ? '보안 위험' : riskLevel === 'warning' ? '주의 / 불필요' : '추가 설정';
      const parentLabel = ec.parent_node ? `📂 ${ec.parent_node}` : '🌐 글로벌 설정';
      const rollbackCmd = ec.rollback_cmd || `no ${ec.command_line}`;
      const escapedRollback = escapeHtml(rollbackCmd).replace(/'/g, "\\'");

      return `
        <div class="extra-item-card ${riskLevel}">
          <div class="extra-item-top">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="extra-risk-badge ${riskLevel}">${riskIcon} ${riskLabel}</span>
              <span class="extra-parent-tag">${escapeHtml(parentLabel)}</span>
            </div>
            <span class="extra-reason-text">${escapeHtml(ec.risk_title || '')}</span>
          </div>

          <div style="font-size:11px; color:var(--text-secondary); margin-bottom:2px;">
            ${escapeHtml(ec.risk_reason || '')}
          </div>

          <!-- 실제 타겟에 추가된 설정 (Diff Highlight) -->
          <div class="extra-diff-box">
            <div class="extra-diff-line">
              <span class="extra-diff-sign">+</span>
              <code>${escapeHtml(ec.command_line)}</code>
            </div>
          </div>

          <!-- 롤백 액션 바 -->
          <div class="extra-rollback-row">
            <div class="flex items-center gap-2" style="min-width:0; flex:1;">
              <span style="font-size:11px; color:var(--text-muted); font-weight:600; white-space:nowrap;">롤백 CLI:</span>
              <code class="extra-rollback-cmd" title="${escapeHtml(rollbackCmd)}">${escapeHtml(rollbackCmd)}</code>
            </div>
            <button class="extra-rollback-btn" onclick="window.copyRollbackCmd(this, '${escapedRollback}')" title="이 명령어만 클립보드에 복사">
              <span>📋</span><span>롤백 복사</span>
            </button>
          </div>
        </div>
      `;
    }).join('');

    extraHtml = `
      <div class="extra-alert-banner ${extraSummary.danger > 0 ? 'has-danger' : ''}">
        <div>
          <div class="extra-alert-title">
            <span>${extraSummary.danger > 0 ? '🚨' : '⚠️'}</span>
            <span>골든 템플릿 외 추가 설정 감지 (${extraCount}건)</span>
          </div>
          <div class="extra-alert-desc">
            골든 룰 준수율과 별개로 장비에 등록된 불필요/보안 위협 명령어가 탐지되었습니다. 
            (보안 위험: <strong style="color:#ff7b72">${extraSummary.danger}</strong>건, 
             주의/불필요: <strong style="color:#ffa657">${extraSummary.warning}</strong>건, 
             일반: <strong>${extraSummary.info}</strong>건)
          </div>
        </div>
        <div class="extra-alert-actions">
          <button class="btn btn-sm btn-primary flex items-center gap-1" onclick="window.switchResultTab('rollback')">
            <span>⚡</span><span>롤백 스크립트 보기</span>
          </button>
        </div>
      </div>
      <div class="extra-items-list">
        ${extraCards}
      </div>
    `;
  }

  // 3. 전체 롤백 스크립트 탭 HTML
  const rollbackTabHtml = `
    <div class="rollback-script-wrapper">
      <div class="rollback-script-header">
        <span>⚡ 자동 생성된 Cisco CLI 롤백 스크립트 전문</span>
        <div class="flex items-center gap-2">
          <button class="btn btn-sm btn-secondary flex items-center gap-1" onclick="window.copyFullRollbackScript(this)">
            <span>📋</span><span>스크립트 복사</span>
          </button>
          ${resultId ? `
            <button class="btn btn-sm btn-secondary flex items-center gap-1" onclick="window.downloadResultRollback('${resultId}')">
              <span>📥</span><span>.cfg 다운로드</span>
            </button>
            <button class="btn btn-sm btn-primary flex items-center gap-1" onclick="window.downloadResultCleanConfig('${resultId}')" title="추가 설정이 제거된 정제된 Clean 설정 파일 다운로드">
              <span>🧹</span><span>Clean Config 다운로드</span>
            </button>
          ` : ''}
        </div>
      </div>
      <pre class="rollback-script-pre" id="rollback-script-content">${escapeHtml(rollbackScript)}</pre>
    </div>
  `;

  // 4. 탭 네비게이션 헤더
  const tabsNavHtml = `
    <div class="result-view-tabs">
      <button class="result-tab-btn active" data-tab="golden" onclick="window.switchResultTab('golden')">
        <span>🛡️ 골든 룰 점검</span>
        <span class="result-tab-badge neutral">${result.passed_items || 0}/${result.total_items || 0}</span>
      </button>
      <button class="result-tab-btn" data-tab="extra" onclick="window.switchResultTab('extra')">
        <span>⚠️ 추가된 설정 Diff</span>
        <span class="result-tab-badge ${extraSummary.danger > 0 ? 'danger' : extraCount > 0 ? 'warning' : 'neutral'}">${extraCount}</span>
      </button>
      <button class="result-tab-btn" data-tab="rollback" onclick="window.switchResultTab('rollback')">
        <span>⚡ 롤백 CLI 스크립트</span>
        ${extraCount > 0 ? `<span class="result-tab-badge info">${extraCount}건</span>` : ''}
      </button>
    </div>
  `;

  const fullContent = `
    ${tabsNavHtml}
    <div id="tab-content-golden" class="result-tab-content" style="display:block;">
      ${sectionHtmls}
    </div>
    <div id="tab-content-extra" class="result-tab-content" style="display:none;">
      ${extraHtml}
    </div>
    <div id="tab-content-rollback" class="result-tab-content" style="display:none;">
      ${rollbackTabHtml}
    </div>
  `;

  if (containerId === 'compare-result-area') {
    area.innerHTML = fullContent;
  } else {
    area.innerHTML = `
      <div class="result-header" style="background: var(--bg-card); border-color: var(--border); margin-bottom: 16px; display:flex; align-items:center; justify-content:space-between; gap:16px; padding:16px 20px; border-radius:var(--radius-lg); border:1px solid var(--border);">
        <div style="display:flex; align-items:center; gap:16px; flex:1; min-width:0;">
          <div class="result-badge ${overall}">${overall}</div>
          <div class="result-info" style="flex:1; min-width:0;">
            <div class="result-hostname" style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
              <span style="font-size:18px; font-weight:700; color:var(--text-primary);">${escapeHtml(displayName)}</span>
              ${(result.hostname && displayName !== result.hostname) ? `<span style="font-size:12px; color:var(--text-muted); font-weight:normal;">(Hostname: <code>${escapeHtml(result.hostname)}</code>)</span>` : ''}
            </div>
            <div class="result-meta" style="margin-top:4px;">
              템플릿: ${escapeHtml(result.template_name || '')} · ${result.passed_items}/${result.total_items} 항목 통과
              ${extraCount > 0 ? ` · <span style="color:#ffa657; font-weight:bold;">⚠️ 추가 설정 ${extraCount}건</span>` : ''}
            </div>
            <div class="score-bar mt-2">
              <div class="score-fill ${overall}" style="width: ${result.score}%"></div>
            </div>
          </div>
        </div>
        <div style="display:flex; align-items:center; gap:16px; flex-shrink:0;">
          <div style="font-size: 32px; font-weight: 800; color: var(--text-secondary)">${result.score}%</div>
        </div>
      </div>
      ${fullContent}
    `;
  }

  area.style.display = 'block';
}
