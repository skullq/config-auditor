// bulk.js — 벌크 업로드 탭

import { api, uploadFiles, initDropZone, setLoading, toast, overallChip, fmtDate } from './app.js';

export function initBulk() {
  const zone  = document.getElementById('bulk-drop-zone');
  const input = document.getElementById('bulk-file-input');
  const runBtn = document.getElementById('bulk-run-btn');

  initDropZone(zone, input, files => handleBulkUpload(files));
  runBtn.addEventListener('click', () => {
    const input = document.getElementById('bulk-file-input');
    if (input.files.length) handleBulkUpload([...input.files]);
    else toast('파일을 먼저 선택하세요.', 'error');
  });
}

async function handleBulkUpload(files) {
  if (!files.length) return;

  const zone = document.getElementById('bulk-drop-zone');
  zone.innerHTML = `<div class="loading-overlay"><div class="spinner"></div><span>${files.length}개 파일 분석 중...</span></div>`;

  const btn = document.getElementById('bulk-run-btn');
  setLoading(btn, true, '처리 중...');

  try {
    const result = await uploadFiles('/api/bulk/upload', files, 'files');
    renderBulkResults(result);
    toast(`벌크 처리 완료: ${result.results.length}개`, 'success');
  } catch (err) {
    toast(`벌크 업로드 실패: ${err.message}`, 'error');
  } finally {
    zone.innerHTML = `
      <div class="drop-icon">📂</div>
      <h3>여러 설정 파일을 드래그하거나 클릭</h3>
      <p>모든 파일이 자동으로 템플릿에 매칭됩니다</p>
    `;
    setLoading(btn, false);
  }
}

function renderBulkResults(data) {
  const results = data.results;
  const jobId = data.job_id;

  // 요약 통계
  const counts = { Pass: 0, Review: 0, Fail: 0, Skipped: 0 };
  results.forEach(r => { counts[r.overall] = (counts[r.overall] || 0) + 1; });

  const summaryHtml = `
    <div class="flex gap-3 mb-3" style="flex-wrap:wrap">
      <div class="card" style="flex:1;min-width:120px;text-align:center;padding:16px">
        <div style="font-size:28px;font-weight:800;color:var(--pass)">${counts.Pass}</div>
        <div class="text-muted">Pass</div>
      </div>
      <div class="card" style="flex:1;min-width:120px;text-align:center;padding:16px">
        <div style="font-size:28px;font-weight:800;color:var(--review)">${counts.Review}</div>
        <div class="text-muted">Review</div>
      </div>
      <div class="card" style="flex:1;min-width:120px;text-align:center;padding:16px">
        <div style="font-size:28px;font-weight:800;color:var(--fail)">${counts.Fail}</div>
        <div class="text-muted">Fail</div>
      </div>
      <div class="card" style="flex:1;min-width:120px;text-align:center;padding:16px">
        <div style="font-size:28px;font-weight:800;color:var(--text-secondary)">${counts.Skipped || 0}</div>
        <div class="text-muted">Skipped</div>
      </div>
    </div>
  `;

  const rowsHtml = results.map(r => `
    <tr>
      <td><code>${r.hostname}</code></td>
      <td style="color:var(--text-secondary);font-size:12px">${r.filename}</td>
      <td>${r.template_name || '—'}</td>
      <td>${overallChip(r.overall)}</td>
      <td>${r.score !== null ? r.score + '%' : '—'}</td>
      <td>
        ${r.result_id
          ? `<button class="btn btn-sm btn-secondary" onclick="window.viewResult('${r.result_id}')">상세</button>
             <button class="btn btn-sm btn-secondary" onclick="window.reportResult('${r.result_id}', '${r.hostname}')">레포트</button>`
          : '<span class="text-muted">—</span>'}
      </td>
    </tr>
  `).join('');

  const exportBtn = `
    <a href="/api/bulk/results/${jobId}/export" class="btn btn-secondary btn-sm" download>
      ⬇ CSV 다운로드
    </a>
  `;

  document.getElementById('bulk-results-area').innerHTML = `
    ${summaryHtml}
    <div class="card">
      <div class="section-header">
        <div class="card-title">📋 세부 결과</div>
        ${exportBtn}
      </div>
      <div style="overflow-x:auto">
        <table class="data-table">
          <thead>
            <tr>
              <th>Hostname</th>
              <th>파일명</th>
              <th>적용 템플릿</th>
              <th>판정</th>
              <th>점수</th>
              <th>액션</th>
            </tr>
          </thead>
          <tbody>${rowsHtml}</tbody>
        </table>
      </div>
    </div>
  `;
  document.getElementById('bulk-results-area').style.display = 'block';
}
