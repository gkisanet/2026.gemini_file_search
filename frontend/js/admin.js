/**
 * 관리자 대시보드 — 프론트엔드 로직
 * 탭 3개: 피드백 교정, 문서 관리, Store 현황
 */

const API = '/api';

// ── 상태 ──────────────────────────────────────────────
const state = {
    token: localStorage.getItem('token'),
    user: JSON.parse(localStorage.getItem('user') || 'null'),
    currentFilter: '',
    rejectTargetId: null,
    selectedFiles: [],
};

// ── 유틸리티 ──────────────────────────────────────────
function $(sel) { return document.querySelector(sel); }

async function api(method, path, body = null) {
    const headers = { 'Content-Type': 'application/json' };
    if (state.token) headers['Authorization'] = `Bearer ${state.token}`;
    const opts = { method, headers };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(`${API}${path}`, opts);
    const data = await res.json();
    if (!res.ok) {
        if (res.status === 401) { logout(); return null; }
        throw new Error(data.detail || '요청 실패');
    }
    return data;
}

function showToast(message, type = 'info') {
    const container = $('#toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}

function logout() {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    window.location.href = '/';
}

// ── 초기화 ────────────────────────────────────────────
(function init() {
    if (!state.token || !state.user || state.user.role !== 'admin') {
        window.location.href = '/';
        return;
    }
    $('#adminUsername').textContent = state.user.username;
    $('#logoutBtn').addEventListener('click', logout);

    loadFeedbacks();
    loadDocuments();
    loadStoreFiles();

    // 필터 버튼
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            state.currentFilter = btn.dataset.filter;
            loadFeedbacks(state.currentFilter);
        });
    });

    // 업로드 버튼 및 파일 선택
    $('#uploadBtn').addEventListener('click', handleUpload);
    $('#btnSelectFiles').addEventListener('click', () => $('#filePicker').click());
    $('#btnSelectFolder').addEventListener('click', () => $('#folderPicker').click());
    $('#filePicker').addEventListener('change', e => updateSelectedFiles(e.target.files));
    $('#folderPicker').addEventListener('change', e => updateSelectedFiles(e.target.files));
    $('#selectedFilesInfo').addEventListener('click', () => {
        state.selectedFiles = [];
        $('#selectedFilesInfo').textContent = "선택된 파일이 없습니다. (버튼 선택 또는 우측 경로 입력)";
        $('#filePicker').value = "";
        $('#folderPicker').value = "";
    });

    // Store 파일 목록 검색/필터 이벤트
    $('#storeFileSearch').addEventListener('input', debounce(() => loadStoreFiles(1), 400));
    $('#storeFileCategoryFilter').addEventListener('change', () => loadStoreFiles(1));
    $('#storeFileTypeFilter').addEventListener('change', () => loadStoreFiles(1));

    // 거절 모달
    $('#rejectCancel').addEventListener('click', () => {
        $('#rejectModal').classList.remove('active');
    });
    $('#rejectConfirm').addEventListener('click', handleReject);

    // 문서 검색
    $('#docSearch').addEventListener('input', debounce(() => {
        loadDocuments($('#docSearch').value.trim());
    }, 300));
})();

function debounce(fn, ms) {
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
}

function updateSelectedFiles(fileList) {
    if (!fileList || fileList.length === 0) return;
    state.selectedFiles = Array.from(fileList);
    $('#selectedFilesInfo').innerHTML = `<span style="color:var(--success)">${state.selectedFiles.length}개 파일이 선택됨</span> (클릭하여 초기화)`;
    $('#uploadPath').value = ""; // 서버경로 지움
}

// ── 피드백 목록 ───────────────────────────────────────
async function loadFeedbacks(status = '') {
    try {
        const query = status ? `?status=${status}` : '';
        const data = await api('GET', `/admin/feedbacks${query}`);
        if (!data) return;

        // 통계
        const s = data.stats || {};
        $('#statPending').textContent = s.pending || 0;
        $('#statApproved').textContent = s.approved || 0;
        $('#statRejected').textContent = s.rejected || 0;
        $('#statTotal').textContent = s.total || 0;

        // 목록
        const container = $('#feedbackList');
        if (!data.corrections || data.corrections.length === 0) {
            container.innerHTML = '<div class="empty-state">교정 피드백이 없습니다</div>';
            return;
        }

        container.innerHTML = data.corrections.map(c => feedbackCardHTML(c)).join('');

        // 승인/거절 버튼 바인딩
        container.querySelectorAll('.btn-approve').forEach(btn => {
            btn.addEventListener('click', () => handleApproval(btn.dataset.id));
        });
        container.querySelectorAll('.btn-reject').forEach(btn => {
            btn.addEventListener('click', () => openRejectModal(btn.dataset.id));
        });
    } catch (err) {
        showToast('피드백 로드 실패: ' + err.message, 'error');
    }
}

function feedbackCardHTML(c) {
    const confidencePct = Math.round((c.confidence || 0) * 100);
    const isPending = c.status === 'pending';

    return `
        <div class="feedback-card">
            <div class="feedback-header">
                <span class="feedback-id">${c.id}</span>
                <span>제출: ${escapeHtml(c.submitted_username)} · ${new Date(c.created_at).toLocaleDateString('ko')}</span>
                <span class="feedback-status ${c.status}">${
                    c.status === 'pending' ? '⏳ 대기' :
                    c.status === 'approved' ? '✅ 승인' : '❌ 거절'
                }</span>
            </div>
            <div class="feedback-body">
                <div class="feedback-field">
                    <span class="feedback-field-label">원래 질문:</span>${escapeHtml(c.original_question)}
                </div>
                <div class="feedback-field">
                    <span class="feedback-field-label">AI 오답:</span>${escapeHtml(c.ai_wrong_answer)}
                </div>
                <div class="feedback-field">
                    <span class="feedback-field-label">교정 내용:</span>${escapeHtml(c.user_correction)}
                </div>
                <div class="feedback-field">
                    <span class="feedback-field-label">추출 사실:</span>${escapeHtml(c.extracted_fact)}
                    <span class="feedback-field-label" style="margin-left:1rem">신뢰도:</span>
                    <span class="confidence-bar"><span class="confidence-fill" style="width:${confidencePct}%"></span></span>
                    ${confidencePct}%
                </div>
            </div>
            ${isPending ? `
                <div class="feedback-actions">
                    <button class="btn-approve" data-id="${c.id}">✅ 승인 (Store 반영)</button>
                    <button class="btn-reject" data-id="${c.id}">❌ 거절</button>
                </div>
            ` : ''}
            ${c.status === 'rejected' && c.reject_reason ? `
                <div class="reject-reason">거절 사유: ${escapeHtml(c.reject_reason)}</div>
            ` : ''}
        </div>
    `;
}

async function handleApproval(correctionId) {
    try {
        await api('POST', `/admin/feedbacks/${correctionId}/approve`);
        showToast('교정이 승인되어 Store에 반영되었습니다', 'success');
        loadFeedbacks(state.currentFilter);
    } catch (err) {
        showToast('승인 실패: ' + err.message, 'error');
    }
}

function openRejectModal(correctionId) {
    state.rejectTargetId = correctionId;
    $('#rejectReason').value = '';
    $('#rejectModal').classList.add('active');
}

async function handleReject() {
    const reason = $('#rejectReason').value.trim();
    if (!reason) { showToast('거절 사유를 입력하세요', 'error'); return; }
    try {
        await api('POST', `/admin/feedbacks/${state.rejectTargetId}/reject`, { reason });
        $('#rejectModal').classList.remove('active');
        showToast('교정이 거절되었습니다', 'info');
        loadFeedbacks(state.currentFilter);
    } catch (err) {
        showToast('거절 실패: ' + err.message, 'error');
    }
}

// ── 문서 관리 ─────────────────────────────────────────
async function loadDocuments(search = '') {
    try {
        const query = search ? `?search=${encodeURIComponent(search)}` : '';
        const data = await api('GET', `/admin/documents${query}`);
        if (!data) return;

        const container = $('#docList');
        $('#docTotalGroups').textContent = data.total_groups || 0;
        $('#docTotalFiles').textContent = data.total_documents || 0;

        if (!data.groups || data.groups.length === 0) {
            container.innerHTML = '<div class="empty-state">업로드된 문서가 없습니다</div>';
            return;
        }

        container.innerHTML = data.groups.map(g => docGroupHTML(g)).join('');

        // 최신 버전 지정 버튼
        container.querySelectorAll('.btn-set-latest').forEach(btn => {
            btn.addEventListener('click', () => setLatestVersion(btn.dataset.id));
        });
    } catch (err) {
        showToast('문서 목록 로드 실패: ' + err.message, 'error');
    }
}

function docGroupHTML(group) {
    const latest = group.latest;
    const latestLabel = latest
        ? `<span style="color:var(--success);font-weight:600">📌 최신: ${escapeHtml(latest.file_name)}</span>`
        : '<span style="color:var(--warning)">⚠ 최신 버전 미지정</span>';

    const docsHtml = group.documents.map(d => {
        const isLatest = d.is_latest;
        const dateLabel = d.version_date
            ? `${d.version_date.slice(0,4)}-${d.version_date.slice(4,6)}-${d.version_date.slice(6,8)}`
            : '날짜 없음';
        return `
            <div class="doc-version-row ${isLatest ? 'is-latest' : ''}">
                <span class="doc-filename">${isLatest ? '📌 ' : '📄 '}${escapeHtml(d.file_name)}</span>
                <span class="doc-date">${dateLabel}</span>
                <span class="doc-uploader">${escapeHtml(d.uploaded_username || '-')}</span>
                ${!isLatest ? `<button class="btn-set-latest" data-id="${d.id}" title="최신 버전으로 지정">⭐ 최신 지정</button>` : '<span class="latest-badge">✅ 최신</span>'}
            </div>
        `;
    }).join('');

    return `
        <div class="doc-group-card">
            <div class="doc-group-header">
                <span class="doc-group-name">📂 ${escapeHtml(group.version_group)}</span>
                <span class="doc-group-count">${group.documents.length}개 버전</span>
                ${latestLabel}
            </div>
            <div class="doc-version-list">${docsHtml}</div>
        </div>
    `;
}

async function setLatestVersion(docId) {
    try {
        const data = await api('PUT', `/admin/documents/${docId}/set-latest`);
        if (data) {
            showToast(data.message, 'success');
            loadDocuments($('#docSearch').value.trim());
        }
    } catch (err) {
        showToast('최신 버전 지정 실패: ' + err.message, 'error');
    }
}

// ── Store 파일 목록 (페이지네이션 + 검색 + 필터) ─────────
let storeFilePage = 1;
const STORE_FILE_LIMIT = 20;

async function loadStoreFiles(page = 1) {
    storeFilePage = page;
    const search = $('#storeFileSearch').value.trim();
    const category = $('#storeFileCategoryFilter').value;
    const storeType = $('#storeFileTypeFilter').value;

    try {
        const params = new URLSearchParams({
            page, limit: STORE_FILE_LIMIT, search, category, store_type: storeType
        });
        const data = await api('GET', `/admin/store_files?${params}`);
        if (!data) return;

        // 요약
        $('#storeFileSummary').textContent = `총 ${data.total}개 파일 · ${data.page}/${data.total_pages} 페이지`;

        // 카테고리 필터 옵션 동적 생성 (첫 로드 시만)
        const catSelect = $('#storeFileCategoryFilter');
        if (catSelect.options.length <= 1 && data.categories.length > 0) {
            data.categories.forEach(c => {
                const opt = document.createElement('option');
                opt.value = c.name === '미분류' ? '' : c.name;
                opt.textContent = `${c.name} (${c.count})`;
                catSelect.appendChild(opt);
            });
        }

        // 테이블 바디
        const tbody = $('#storeFileTableBody');
        if (data.files.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="padding:2rem;text-align:center;color:var(--text-muted)">파일이 없습니다</td></tr>';
        } else {
            const startIdx = (data.page - 1) * data.limit;
            tbody.innerHTML = data.files.map((f, i) => {
                const size = f.file_size ? formatFileSize(f.file_size) : '-';
                const catBadge = f.category
                    ? `<span style="padding:0.15rem 0.4rem;border-radius:4px;font-size:0.75rem;background:rgba(108,92,231,0.15);color:var(--accent-secondary)">${escapeHtml(f.category)}</span>`
                    : '<span style="color:var(--text-muted)">미분류</span>';
                const storeBadge = f.store_type === 'primary'
                    ? '<span style="color:var(--info)">원본</span>'
                    : '<span style="color:var(--warning)">교정</span>';
                const date = f.created_at ? f.created_at.split('T')[0] : '-';
                return `<tr style="border-bottom:1px solid rgba(255,255,255,0.03);">
                    <td style="padding:0.5rem;color:var(--text-muted)">${startIdx + i + 1}</td>
                    <td style="padding:0.5rem;max-width:400px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escapeHtml(f.file_name)}">${escapeHtml(f.file_name)}</td>
                    <td style="padding:0.5rem">${catBadge}</td>
                    <td style="padding:0.5rem">${storeBadge}</td>
                    <td style="padding:0.5rem;text-align:right;color:var(--text-muted)">${size}</td>
                    <td style="padding:0.5rem;color:var(--text-muted)">${date}</td>
                </tr>`;
            }).join('');
        }

        // 페이지네이션 렌더링
        renderStoreFilePagination(data.page, data.total_pages);
    } catch (err) {
        console.error('Store 파일 목록 로드 실패:', err);
    }
}

function renderStoreFilePagination(current, total) {
    const container = $('#storeFilePagination');
    if (total <= 1) { container.innerHTML = ''; return; }

    let html = '';
    const btnStyle = 'padding:0.35rem 0.7rem;border-radius:var(--radius-sm);border:1px solid var(--border-glass);background:var(--bg-glass);color:var(--text-secondary);cursor:pointer;font-size:0.85rem;';
    const activeStyle = 'padding:0.35rem 0.7rem;border-radius:var(--radius-sm);border:1px solid var(--accent-primary);background:var(--accent-primary);color:white;cursor:default;font-size:0.85rem;';

    // 이전 버튼
    if (current > 1) html += `<button style="${btnStyle}" onclick="loadStoreFiles(${current - 1})">◀</button>`;
    
    // 페이지 번호 (최대 7개 표시)
    let startP = Math.max(1, current - 3);
    let endP = Math.min(total, current + 3);
    if (startP > 1) html += `<button style="${btnStyle}" onclick="loadStoreFiles(1)">1</button><span style="color:var(--text-muted)">…</span>`;
    for (let p = startP; p <= endP; p++) {
        html += `<button style="${p === current ? activeStyle : btnStyle}" onclick="loadStoreFiles(${p})">${p}</button>`;
    }
    if (endP < total) html += `<span style="color:var(--text-muted)">…</span><button style="${btnStyle}" onclick="loadStoreFiles(${total})">${total}</button>`;
    
    // 다음 버튼
    if (current < total) html += `<button style="${btnStyle}" onclick="loadStoreFiles(${current + 1})">▶</button>`;
    
    container.innerHTML = html;
}

function formatFileSize(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return (bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0) + ' ' + units[i];
}


async function handleUpload() {
    const path = $('#uploadPath').value.trim();
    const storeType = $('#uploadStore').value;
    const versionGroup = $('#uploadVersionGroup') ? $('#uploadVersionGroup').value.trim() : '';
    
    if (!path && state.selectedFiles.length === 0) { 
        showToast('파일/폴더를 선택하거나 서버 경로를 입력하세요', 'error'); 
        return; 
    }

    const totalFiles = state.selectedFiles.length || '?';
    const infoEl = $('#selectedFilesInfo');
    const uploadBtn = $('#uploadBtn');
    
    // 업로드 시작 UI 업데이트
    uploadBtn.textContent = '⏳ 업로드 중...';
    uploadBtn.disabled = true;
    
    // 경과 시간 타이머 시작
    const startTime = Date.now();
    const timer = setInterval(() => {
        const elapsed = Math.floor((Date.now() - startTime) / 1000);
        const min = Math.floor(elapsed / 60);
        const sec = elapsed % 60;
        const timeStr = min > 0 ? `${min}분 ${sec}초` : `${sec}초`;
        infoEl.innerHTML = `<span style="color:var(--warning)">⏳ ${totalFiles}개 파일 업로드 + AI 인덱싱 진행 중... (${timeStr} 경과)</span><br><span style="font-size:0.8rem;color:var(--text-muted)">파일당 최대 수 분 소요될 수 있습니다. 터미널 로그에서 진행 상황을 확인하세요.</span>`;
    }, 1000);

    try {
        let data;

        if (state.selectedFiles.length > 0) {
            const formData = new FormData();
            for (const f of state.selectedFiles) {
                formData.append('files', f);
            }
            formData.append('store_type', storeType);
            formData.append('version_group', versionGroup);
            
            const res = await fetch(`${API}/admin/upload_client`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${state.token}` },
                body: formData
            });
            data = await res.json();
            if (!res.ok) throw new Error(data.detail || '업로드 실패');
        } else {
            data = await api('POST', '/admin/upload', {
                path,
                store_type: storeType,
                version_group: versionGroup,
            });
        }

        if (data) {
            showToast(data.message, 'success');
            // reset files
            state.selectedFiles = [];
            infoEl.textContent = "선택된 파일이 없습니다. (버튼 또는 경로 입력)";
            $('#uploadPath').value = "";
            $('#filePicker').value = "";
            $('#folderPicker').value = "";
            $('#uploadVersionGroup').value = "";

            loadDocuments();
            loadStoreFiles();
        }
    } catch (err) {
        showToast('업로드 실패: ' + err.message, 'error');
        infoEl.innerHTML = `<span style="color:var(--danger)">❌ 업로드 실패: ${escapeHtml(err.message)}</span>`;
    } finally {
        clearInterval(timer);
        uploadBtn.textContent = '🚀 업로드';
        uploadBtn.disabled = false;
    }
}
