// report.js — 레포트 탭 기능 및 SSE 스트리밍

import { api, toast } from './app.js';

export function initReport() {
    // 탭 열리면 자동 로드 이벤트 바인딩 (app.js에서 탭 전환시 로드하게 해도 무방)
    document.querySelector('[data-tab="tab-report"]').addEventListener('click', loadReportHistory);
    
    document.getElementById('report-bulk-btn').addEventListener('click', runBulkLLM);
    
    loadReportHistory();
}

async function loadReportHistory() {
    try {
        const results = await api('/api/reports/list');
        const tbody = document.getElementById('report-history-body');
        
        if (!results || results.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty-state">검사 이력이 없습니다</td></tr>';
            return;
        }
        
        // 전역변수로 리스트 들고 있기 위해
        window._reportItems = results;

        tbody.innerHTML = results.map(r => `
          <tr id="rep-row-${r.id}">
            <td><code>${r.hostname}</code></td>
            <td>${r.template_name}</td>
            <td>${r.overall} (${r.score}%)</td>
            <td id="rep-status-${r.id}">${r.has_report ? '✅ 생성됨' : '➖ 없음'}</td>
            <td>
              <div style="display:flex; gap:16px; align-items:center;">
                <!-- 데이터 & 결과 다운로드 그룹 -->
                <div style="display:flex; flex-direction:column; gap:4px; min-width:140px;">
                  <button class="btn btn-sm btn-secondary" onclick="window.downloadCompareData('${r.id}')" style="text-align:left;">💾 비교자료 다운로드</button>
                  ${r.has_report ? `<button class="btn btn-sm btn-secondary" onclick="window.downloadReport('${r.id}')" style="text-align:left;">⬇ LLM 분석결과 다운로드</button>` : ''}
                </div>
                
                <!-- 기능 및 제어 그룹 -->
                <div style="display:flex; flex-direction:column; gap:4px; border-left:1px solid var(--border); padding-left:16px;">
                  <button class="btn btn-sm btn-primary" onclick="window.generateLLMReport('${r.id}')">
                    ${r.has_report ? '🔄 LLM 레포트 재생성' : '✨ LLM 생성'}
                  </button>
                  <button class="btn btn-sm btn-danger" onclick="window.deleteReport('${r.id}', '${r.hostname}')">🗑️ 내역 삭제</button>
                </div>
              </div>
            </td>
          </tr>
        `).join('');
    } catch {}
}

window.downloadCompareData = (id) => {
    window.location.href = `/api/compare/download/${id}`;
};

window.deleteReport = async (id, hostname) => {
    if (!confirm(`"${hostname}"의 결과 데이터와 레포트를 삭제하시겠습니까?`)) return;
    try {
        await fetch(`/api/compare/results/${id}`, { method: 'DELETE' });
        toast('결과가 삭제되었습니다.', 'success');
        loadReportHistory();
    } catch (e) {
        toast('삭제 실패', 'error');
    }
};

window.deleteDuplicateReports = async () => {
    if (!confirm("동일한 Hostname을 가진 과거 중복 내역을 모두 삭제하고, 최신 검사 결과 1건씩만 남기시겠습니까?")) return;
    try {
        const res = await fetch(`/api/reports/duplicates`, { method: 'DELETE' });
        if (!res.ok) throw new Error("API 오류");
        const data = await res.json();
        toast(data.message || '중복 이력이 성공적으로 정리되었습니다.', 'success');
        loadReportHistory();
    } catch (e) {
        toast('중복 이력 삭제 실패', 'error');
    }
};

window.downloadReport = (id) => {
    window.location.href = `/api/reports/download/${id}`;
};

// 개별 LLM 생성 (스트리밍 대화형 모달 UI)
window.generateLLMReport = async (id) => {
    const r = window._reportItems?.find(x => x.id === id);
    if(!r) return;
    
    const modal = document.getElementById('llm-modal');
    const outTitle = document.getElementById('llm-modal-title');
    const outPre = document.getElementById('llm-modal-body');
    const statusDiv = document.getElementById('llm-modal-status');
    const actionDiv = document.getElementById('llm-modal-action');
    const closeBtn = document.getElementById('llm-modal-close');
    const statusTd = document.getElementById(`rep-status-${id}`);
    
    // 모달 초기화 및 열기
    modal.style.display = 'flex';
    outTitle.textContent = `✨ [${r.hostname}] LLM 레포트 작성 중...`;
    outPre.textContent = '';
    statusDiv.innerHTML = '<div class="spinner" style="width:14px;height:14px;display:inline-block"></div> LLM과 통신하며 분석 중입니다...';
    actionDiv.innerHTML = '';
    statusTd.innerHTML = '<div class="spinner" style="width:14px;height:14px;display:inline-block"></div> 생성 중...';
    
    // 닫기 이벤트 임시 정리
    const closeModal = () => modal.style.display = 'none';
    closeBtn.onclick = closeModal;

    const abortController = new AbortController();
    actionDiv.innerHTML = `<button id="llm-modal-abort-btn" class="btn btn-sm btn-danger">⏹️ 생성 중단하기</button>`;
    document.getElementById('llm-modal-abort-btn').onclick = () => {
        abortController.abort();
    };

    try {
        const response = await fetch(`/api/llm/report/stream/${id}`, { signal: abortController.signal });
        if (!response.ok) throw new Error('스트림 요청 실패');

        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = '';

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            console.log("Chunk received:", value.length, "bytes");
            buffer += decoder.decode(value, { stream: true });
            
            // SSE 스펙에 따른 라인 분리
            let parts = buffer.split('\n');
            buffer = parts.pop(); 
            
            for (let line of parts) {
                line = line.trim();
                if (!line) continue;
                
                if (line.startsWith('data: ')) {
                    const dataStr = line.substring(6).trim();
                    if (dataStr === '[DONE]') continue;
                    try {
                        const parsed = JSON.parse(dataStr);
                        if (parsed.text) {
                            outPre.textContent += parsed.text;
                            outPre.scrollTop = outPre.scrollHeight;
                        } else if (parsed.error) {
                            outPre.innerHTML += `<div style="color:var(--danger); padding:10px; border:1px solid var(--danger); margin-top:10px;">❌ LLM 에러 발생: ${parsed.error}</div>`;
                        } else if (parsed.debug) {
                            console.log("DEBUG FROM SERVER:", parsed.debug);
                        }
                    } catch (e) {
                        console.warn("JSON parse error", e);
                    }
                }
            }
        }
        
        outTitle.textContent = `✅ [${r.hostname}] 레포트 작성 완료`;
        statusDiv.innerHTML = '<span style="color:var(--success)">✅ 레포트 생성이 완료되었습니다.</span>';
        
        // 다운로드 버튼과 닫기 버튼을 모달 하단에 배치
        actionDiv.innerHTML = `
            <div style="display:flex; gap:10px; justify-content:center; margin-top:10px;">
                <a href="/api/reports/download/${id}" class="btn btn-primary" id="final-download-link">⬇ 최종 레포트 다운로드</a>
                <button class="btn btn-secondary" onclick="document.getElementById('llm-modal').style.display='none'">닫기</button>
            </div>
        `;
        
        statusTd.innerHTML = '✅ 생성됨';
        toast(`[${r.hostname}] 레포트가 생성 완료되었습니다.`, 'success');
        
        // 데이터가 시스템에 반영될 시간을 주기 위해 약간 지연 후 갱신
        setTimeout(loadReportHistory, 800);

        
    } catch (err) {
        if (err.name === 'AbortError') {
            statusTd.innerHTML = '➖ 중단됨';
            statusDiv.innerHTML = '<span style="color:var(--warning)">⚠️ 사용자에 의해 생성이 중단되었습니다.</span>';
            actionDiv.innerHTML = `<button class="btn btn-secondary" onclick="document.getElementById('llm-modal').style.display='none'">닫기</button>`;
            toast('LLM 생성이 중단되었습니다.', 'warning');
        } else {
            statusTd.innerHTML = '❌ 실패';
            statusDiv.innerHTML = '<span style="color:var(--danger)">❌ 레포트 생성에 실패했습니다.</span>';
            actionDiv.innerHTML = `<button class="btn btn-secondary" onclick="document.getElementById('llm-modal').style.display='none'">닫기</button>`;
            outPre.textContent += '\n\n[시스템 에러 발생] ' + err.message;
            toast('레포트 생성 중 오류', 'error');
        }
    }
};

// 벌크 LLM 생성 (현재 목록 중 없음 상태인 것들을 순차적으로 실행)
async function runBulkLLM() {
    if(!window._reportItems || window._reportItems.length === 0) return;
    
    const targets = window._reportItems.filter(r => !r.has_report);
    if(targets.length === 0) {
        toast('모든 결과에 이미 레포트가 생성되어 있습니다.', 'info');
        return;
    }
    
    if(!confirm(`${targets.length}개 항목에 대해 순차적으로 LLM 레포트를 자동 생성하시겠습니까? 시간이 걸릴 수 있습니다.`)) return;
    
    for (let i = 0; i < targets.length; i++) {
        await window.generateLLMReport(targets[i].id);
        // 서버/Ollama 부하를 위해 짧은 대기
        await new Promise(res => setTimeout(res, 2000));
    }
    
    toast('모든 벌크 생성이 완료되었습니다.', 'success');
}
