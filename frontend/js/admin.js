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
    loadStores();

    // 필터 버튼
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            state.currentFilter = btn.dataset.filter;
            loadFeedbacks(state.currentFilter);
        });
    });

    // 업로드 버튼
    $('#uploadBtn').addEventListener('click', handleUpload);

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

// ── Store 현황 ────────────────────────────────────────
async function loadStores() {
    try {
        const data = await api('GET', '/admin/stores');
        if (!data) return;

        const container = $('#storeList');
        if (!data.stores || data.stores.length === 0) {
            container.innerHTML = '<div class="empty-state">File Search Store가 없습니다</div>';
            return;
        }

        container.innerHTML = data.stores.map(s => `
            <div class="store-card">
                <div class="store-name">${escapeHtml(s.display_name || s.name)}</div>
                <div class="store-doc-count">📄 문서 수: ${s.document_count || 0}개</div>
            </div>
        `).join('');
    } catch (err) {
        console.error('Store 로드 실패:', err);
    }
}

// ── 업로드 ────────────────────────────────────────────
async function handleUpload() {
    const path = $('#uploadPath').value.trim();
    const storeType = $('#uploadStore').value;
    const versionGroup = $('#uploadVersionGroup') ? $('#uploadVersionGroup').value.trim() : '';
    if (!path) { showToast('파일 경로를 입력하세요', 'error'); return; }

    try {
        const data = await api('POST', '/admin/upload', {
            path,
            store_type: storeType,
            version_group: versionGroup,
        });
        if (data) {
            showToast(data.message, 'success');
            loadDocuments();
            loadStores();
        }
    } catch (err) {
        showToast('업로드 실패: ' + err.message, 'error');
    }
}
