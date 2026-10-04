// webapp/static/js/impact.js
// 템플릿 변경사항 전역 감지, 부수적 영향도 분석 및 승인/롤백 결정 컨트롤러

let currentPendingTemplates = [];
let activeImpactTemplateId = null;

/**
 * 전역 템플릿 변경사항을 조회하여 헤더 뱃지, 상단 알림 배너, 퀵 알림 버튼을 갱신합니다.
 */
export async function checkPendingTemplateChanges() {
  try {
    const res = await fetch('/api/golden/pending-changes?_=' + Date.now());
    if (!res.ok) return;
    const pending = await res.json();
    currentPendingTemplates = pending || [];

    const banner = document.getElementById('global-template-impact-banner');
    const goldenBadge = document.getElementById('nav-golden-pending-badge');
    const compareBadge = document.getElementById('nav-compare-pending-badge');
    const headerPill = document.getElementById('header-pending-change-pill');
    const bannerTitle = document.getElementById('impact-banner-title');
    const bannerDesc = document.getElementById('impact-banner-desc');
    const pillCountText = document.getElementById('header-pending-count-text');

    if (currentPendingTemplates.length > 0) {
      const first = currentPendingTemplates[0];
      const affectedCount = first.change_summary?.affected_count || 0;
      const totalPendingCount = currentPendingTemplates.length;
      
      if (banner) {
        banner.style.display = 'block';
        if (bannerTitle) {
          bannerTitle.innerHTML = `⚠️ [골든 템플릿 변경 감지] <strong>"${escapeHtml(first.name)}"</strong> 기준 룰이 수정되었습니다.`;
        }
        if (bannerDesc) {
          bannerDesc.textContent = `Compare 탭에 연결된 ${affectedCount}개 장비의 감사 판정에 영향을 미칩니다. 변경 내역을 확인하고 일괄 재감사를 허용할지, 아니면 원래 버전으로 롤백할지 결정하세요.`;
        }
      }
      if (goldenBadge) goldenBadge.style.display = 'inline-flex';
      if (compareBadge) compareBadge.style.display = 'inline-flex';
      
      if (headerPill) {
        headerPill.style.display = 'inline-flex';
        if (pillCountText) {
          pillCountText.textContent = `⚠️ 템플릿 변경 (${totalPendingCount}건)`;
        }
      }
    } else {
      if (banner) banner.style.display = 'none';
      if (goldenBadge) goldenBadge.style.display = 'none';
      if (compareBadge) compareBadge.style.display = 'none';
      if (headerPill) headerPill.style.display = 'none';
    }
  } catch (err) {
    console.error('checkPendingTemplateChanges error:', err);
  }
}

/**
 * 템플릿 변경 영향 분석 및 승인/롤백 모달 열기
 */
export async function openTemplateImpactModal(templateId = null) {
  const modal = document.getElementById('template-impact-modal');
  if (!modal) return;

  // 1. 클릭 즉시 모달을 열어 지연 없는 즉각 반응성 제공 (0ms 피드백)
  modal.style.display = 'flex';

  let tpl = null;
  try {
    const res = await fetch('/api/golden/pending-changes?_=' + Date.now());
    if (res.ok) {
      currentPendingTemplates = (await res.json()) || [];
    }
  } catch (e) {
    console.error(e);
  }

  if (templateId) {
    tpl = currentPendingTemplates.find(t => t.id === templateId);
  } else if (currentPendingTemplates.length > 0) {
    tpl = currentPendingTemplates[0];
  }

  if (!tpl && templateId) {
    try {
      const res = await fetch(`/api/golden/templates/${templateId}?_=` + Date.now());
      if (res.ok) tpl = await res.json();
    } catch (e) {
      console.error(e);
    }
  }

  if (!tpl) {
    const { toast } = await import('./app.js');
    toast('승인/롤백할 템플릿 변경사항이 없습니다.', 'info');
    modal.style.display = 'none';
    return;
  }

  activeImpactTemplateId = tpl.id;
  const summary = tpl.change_summary || {};
  const diff = summary.diff || {};
  const affectedDevices = summary.affected_devices || [];

  // 모달 헤더 채우기
  const titleEl = document.getElementById('impact-modal-tpl-title');
  const subEl = document.getElementById('impact-modal-tpl-subtitle');
  if (titleEl) titleEl.textContent = `골든 템플릿 변경 영향 분석: "${tpl.name}"`;
  if (subEl) subEl.textContent = `OS: ${(tpl.os || 'iosxe').toUpperCase()} | 연동된 Compare 감사 장비: ${affectedDevices.length}대`;

  // 요약 카운트 채우기
  const affectedCountEl = document.getElementById('impact-affected-count');
  const addedCountEl = document.getElementById('impact-added-count');
  const removedCountEl = document.getElementById('impact-removed-count');
  const modCountEl = document.getElementById('impact-modified-count');

  if (affectedCountEl) affectedCountEl.textContent = `${affectedDevices.length}대`;
  if (addedCountEl) addedCountEl.textContent = `+${(diff.added || []).length}개`;
  if (removedCountEl) removedCountEl.textContent = `-${(diff.removed || []).length}개`;
  if (modCountEl) modCountEl.textContent = `~${(diff.modified || []).length}개`;

  // 1. 규칙 Diff 렌더링
  const diffListEl = document.getElementById('impact-rule-diff-list');
  if (diffListEl) {
    let diffHtml = '';
    const added = diff.added || [];
    const removed = diff.removed || [];
    const modified = diff.modified || [];

    if (added.length === 0 && removed.length === 0 && modified.length === 0) {
      diffHtml = `<div class="empty-state text-muted py-3" style="text-align:center; padding:16px;">규칙 내용에는 변경사항이 없으며 기본 메타데이터(설명/이름 등)가 업데이트되었습니다.</div>`;
    } else {
      added.forEach(item => {
        diffHtml += `
          <div class="impact-diff-item diff-added">
            <span class="diff-tag tag-added">+ 추가된 룰</span>
            <code class="diff-code">${escapeHtml(item.command_line)}</code>
            <span class="diff-meta">기대값: <code>${escapeHtml(item.expected_value || '(존재확인)')}</code> [${item.match_type}]</span>
          </div>
        `;
      });

      removed.forEach(item => {
        diffHtml += `
          <div class="impact-diff-item diff-removed">
            <span class="diff-tag tag-removed">- 삭제된 룰</span>
            <code class="diff-code">${escapeHtml(item.command_line)}</code>
            <span class="diff-meta">이전 기대값: <code>${escapeHtml(item.expected_value || '(존재확인)')}</code> [${item.match_type}]</span>
          </div>
        `;
      });

      modified.forEach(item => {
        const changes = item.changes || {};
        const changeParts = [];
        if (changes.expected_value) {
          changeParts.push(`기대값: "${escapeHtml(changes.expected_value.old)}" → "<strong>${escapeHtml(changes.expected_value.new)}</strong>"`);
        }
        if (changes.match_type) {
          changeParts.push(`매칭방식: [${changes.match_type.old}] → [<strong>${changes.match_type.new}</strong>]`);
        }
        if (changes.full_line_mode !== undefined) {
          changeParts.push(`전체라인모드: ${changes.full_line_mode.new ? 'ON' : 'OFF'}`);
        }

        diffHtml += `
          <div class="impact-diff-item diff-modified">
            <span class="diff-tag tag-modified">~ 변경된 룰</span>
            <code class="diff-code">${escapeHtml(item.command_line)}</code>
            <span class="diff-meta">${changeParts.join(' | ')}</span>
          </div>
        `;
      });
    }
    diffListEl.innerHTML = diffHtml;
  }

  // 2. 영향받는 장비 목록 테이블 렌더링
  const tbody = document.getElementById('impact-devices-tbody');
  if (tbody) {
    if (affectedDevices.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted py-3" style="text-align:center; padding:16px;">이 템플릿과 연동된 기존 Compare 장비가 없습니다.</td></tr>`;
    } else {
      tbody.innerHTML = affectedDevices.map(d => {
        const score = typeof d.score === 'number' ? Math.round(d.score) : 0;
        const scoreClass = score >= 100 ? 'badge-exact' : 'badge-fail';
        return `
          <tr>
            <td style="font-weight:700; color:var(--text-primary);">🖥️ ${escapeHtml(d.hostname || 'Unknown')}</td>
            <td class="text-muted text-xs"><code>${escapeHtml(d.filename || d.hostname)}</code></td>
            <td><span class="guide-badge ${scoreClass}">${score}%</span></td>
            <td><span class="chip chip-${d.overall?.toLowerCase() || 'skip'}">${d.overall || 'N/A'}</span></td>
            <td class="text-xs" style="color:var(--review); font-weight:600;">
              ⚠️ 새 골든 룰 적용 시 준수율 변동 및 Diff/롤백 CLI 즉시 재계산
            </td>
          </tr>
        `;
      }).join('');
    }
  }

  modal.style.display = 'flex';
}

/**
 * 모달 닫기
 */
export function closeTemplateImpactModal() {
  const modal = document.getElementById('template-impact-modal');
  if (modal) modal.style.display = 'none';
  activeImpactTemplateId = null;
}

/**
 * 템플릿 변경사항에 대한 사용자 결정 제출 (허용/재감사 또는 롤백)
 */
export async function submitTemplateImpactDecision(action) {
  if (!activeImpactTemplateId) return;

  const btnAccept = document.getElementById('impact-accept-btn');
  const btnRollback = document.getElementById('impact-rollback-btn');
  const { toast, setLoading } = await import('./app.js');

  const activeBtn = action === 'accept' ? btnAccept : btnRollback;
  setLoading(activeBtn, true, action === 'accept' ? '재감사 적용 중...' : '롤백 복원 중...');

  try {
    const res = await fetch('/api/golden/resolve-change', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        template_id: activeImpactTemplateId,
        action: action
      })
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || '요청 실패');
    }

    const data = await res.json();
    closeTemplateImpactModal();

    toast(data.message, action === 'accept' ? 'success' : 'info');

    // UI 전체 동기화
    await checkPendingTemplateChanges();
    if (window.loadGoldenTemplates) {
      window.loadGoldenTemplates();
    }
    if (window.loadCompareTree) {
      window.loadCompareTree();
    }
  } catch (err) {
    toast(`처리 실패: ${err.message}`, 'error');
  } finally {
    setLoading(activeBtn, false);
  }
}

// 전역 윈도우 바인딩
window.checkPendingTemplateChanges = checkPendingTemplateChanges;
window.openTemplateImpactModal = openTemplateImpactModal;
window.closeTemplateImpactModal = closeTemplateImpactModal;
window.submitTemplateImpactDecision = submitTemplateImpactDecision;

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
