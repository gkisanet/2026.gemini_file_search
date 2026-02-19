/**
 * 사내 규정 RAG 챗봇 — 프론트엔드 앱 로직
 * 인증, 세션 관리(사이드바 히스토리), 채팅, 피드백 제출
 */

const API = '/api';

// ── 상태 관리 ─────────────────────────────────────────
const state = {
    token: localStorage.getItem('token'),
    user: JSON.parse(localStorage.getItem('user') || 'null'),
    currentSessionId: null,
    messages: [],       // 현재 세션의 메시지 배열
    sessions: [],       // 사이드바 세션 목록
    feedbackTargetIndex: null,  // 피드백 대상 메시지 인덱스
};

// ── 유틸리티 ──────────────────────────────────────────
function $(sel) { return document.querySelector(sel); }
function $$(sel) { return document.querySelectorAll(sel); }

/** API 호출 헬퍼 */
async function api(method, path, body = null) {
    const headers = { 'Content-Type': 'application/json' };
    if (state.token) headers['Authorization'] = `Bearer ${state.token}`;

    const opts = { method, headers };
    if (body) opts.body = JSON.stringify(body);

    const res = await fetch(`${API}${path}`, opts);
    const data = await res.json();

    if (!res.ok) {
        // 인증 만료 시 로그아웃
        if (res.status === 401) { logout(); return null; }
        throw new Error(data.detail || '요청 실패');
    }
    return data;
}

/** 토스트 알림 */
function showToast(message, type = 'info') {
    const container = $('#toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

/** 마크다운 간이 렌더링 (코드블록, 볼드, 줄바꿈) */
function renderMarkdown(text) {
    return text
        .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\n/g, '<br>');
}

// ── 인증 ──────────────────────────────────────────────
$('#loginForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = $('#username').value.trim();
    const password = $('#password').value;

    try {
        const data = await api('POST', '/auth/login', { username, password });
        if (data) {
            state.token = data.token;
            state.user = data.user;
            localStorage.setItem('token', data.token);
            localStorage.setItem('user', JSON.stringify(data.user));
            showApp();
        }
    } catch (err) {
        $('#loginError').textContent = err.message;
    }
});

function logout() {
    state.token = null;
    state.user = null;
    state.currentSessionId = null;
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    showLogin();
}

function showLogin() {
    $('#loginView').style.display = 'flex';
    $('#appView').classList.remove('active');
}

function showApp() {
    $('#loginView').style.display = 'none';
    $('#appView').classList.add('active');
    $('#usernameDisplay').textContent = state.user.username;
    $('#roleDisplay').textContent = state.user.role;
    // 관리자면 관리 링크 표시
    if (state.user.role === 'admin') {
        $('#adminLink').style.display = 'inline-block';
    }
    loadSessions();
}

$('#logoutBtn').addEventListener('click', logout);

// ── 사이드바 토글 ─────────────────────────────────────
$('#sidebarToggle').addEventListener('click', () => {
    const sidebar = $('#sidebar');
    sidebar.classList.toggle('hidden');
});

// ── 세션 관리 (사이드바 히스토리) ──────────────────────
async function loadSessions() {
    try {
        const data = await api('GET', '/sessions');
        if (!data) return;
        state.sessions = data.sessions || [];
        renderSessionList();
    } catch (err) {
        console.error('세션 목록 로드 실패:', err);
    }
}

function renderSessionList() {
    const list = $('#sessionList');

    if (state.sessions.length === 0) {
        list.innerHTML = '<div class="session-group-label">대화 없음</div>';
        return;
    }

    // 날짜별 그룹핑
    const now = new Date();
    const today = now.toDateString();
    const yesterday = new Date(now - 86400000).toDateString();

    const groups = { today: [], yesterday: [], older: [] };

    state.sessions.forEach(s => {
        const d = new Date(s.updated_at).toDateString();
        if (d === today) groups.today.push(s);
        else if (d === yesterday) groups.yesterday.push(s);
        else groups.older.push(s);
    });

    let html = '';

    if (groups.today.length) {
        html += '<div class="session-group-label">오늘</div>';
        html += groups.today.map(s => sessionItemHTML(s)).join('');
    }
    if (groups.yesterday.length) {
        html += '<div class="session-group-label">어제</div>';
        html += groups.yesterday.map(s => sessionItemHTML(s)).join('');
    }
    if (groups.older.length) {
        html += '<div class="session-group-label">이전</div>';
        html += groups.older.map(s => sessionItemHTML(s)).join('');
    }

    list.innerHTML = html;

    // 클릭 이벤트
    list.querySelectorAll('.session-item').forEach(el => {
        el.addEventListener('click', (e) => {
            if (e.target.classList.contains('session-item-delete')) return;
            loadSession(el.dataset.id);
        });
    });

    list.querySelectorAll('.session-item-delete').forEach(el => {
        el.addEventListener('click', (e) => {
            e.stopPropagation();
            deleteSession(el.dataset.id);
        });
    });
}

function sessionItemHTML(s) {
    const active = s.id === state.currentSessionId ? 'active' : '';
    const title = s.title || '새 대화';
    return `
        <div class="session-item ${active}" data-id="${s.id}">
            <span class="session-item-title">📄 ${escapeHtml(title)}</span>
            <button class="session-item-delete" data-id="${s.id}" title="삭제">✕</button>
        </div>
    `;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ── 새 대화 생성 ──────────────────────────────────────
$('#newChatBtn').addEventListener('click', async () => {
    try {
        const data = await api('POST', '/sessions');
        if (data) {
            state.currentSessionId = data.session_id;
            state.messages = [];
            renderChat();
            await loadSessions();
        }
    } catch (err) {
        showToast('새 대화 생성 실패: ' + err.message, 'error');
    }
});

// ── 세션 로드 ─────────────────────────────────────────
async function loadSession(sessionId) {
    try {
        const data = await api('GET', `/sessions/${sessionId}`);
        if (!data) return;
        state.currentSessionId = sessionId;
        state.messages = data.messages || [];
        renderChat();
        renderSessionList();
    } catch (err) {
        showToast('대화 로드 실패: ' + err.message, 'error');
    }
}

// ── 세션 삭제 ─────────────────────────────────────────
async function deleteSession(sessionId) {
    try {
        await api('DELETE', `/sessions/${sessionId}`);
        if (state.currentSessionId === sessionId) {
            state.currentSessionId = null;
            state.messages = [];
            renderChat();
        }
        await loadSessions();
        showToast('대화가 삭제되었습니다', 'success');
    } catch (err) {
        showToast('삭제 실패: ' + err.message, 'error');
    }
}

// ── 채팅 렌더링 ───────────────────────────────────────
function renderChat() {
    const container = $('#chatMessages');
    const empty = $('#chatEmpty');

    if (!state.currentSessionId || state.messages.length === 0) {
        empty.style.display = 'flex';
        // 빈 상태에서도 메시지 영역 비우기
        const msgElements = container.querySelectorAll('.message');
        msgElements.forEach(el => el.remove());
        return;
    }

    empty.style.display = 'none';

    // 메시지 영역 비우고 다시 렌더링
    const msgElements = container.querySelectorAll('.message');
    msgElements.forEach(el => el.remove());

    state.messages.forEach((msg, idx) => {
        appendMessage(msg.role, msg.content, msg.citations || [], idx, false);
    });

    scrollToBottom();
}

function appendMessage(role, content, citations = [], index = null, scroll = true) {
    const container = $('#chatMessages');
    const empty = $('#chatEmpty');
    empty.style.display = 'none';

    const div = document.createElement('div');
    div.className = `message ${role}`;

    let html = `<div class="message-bubble">${renderMarkdown(content)}</div>`;

    // Citation 출처 표시
    if (citations && citations.length > 0) {
        html += '<div class="message-citations">';
        citations.forEach(c => {
            const label = c.title || c.uri || '출처';
            html += `<span class="citation-tag">📎 ${escapeHtml(label)}</span>`;
        });
        html += '</div>';
    }

    // AI 메시지에 피드백 버튼
    if (role === 'assistant' && index !== null) {
        html += `
            <div class="message-actions">
                <button class="btn-feedback" data-index="${index}" title="이 답변이 틀렸다면 피드백을 남겨주세요">
                    👎 오답 신고
                </button>
            </div>
        `;
    }

    div.innerHTML = html;
    container.appendChild(div);

    // 피드백 버튼 이벤트
    const fbBtn = div.querySelector('.btn-feedback');
    if (fbBtn) {
        fbBtn.addEventListener('click', () => openFeedbackModal(parseInt(fbBtn.dataset.index)));
    }

    if (scroll) scrollToBottom();
}

function scrollToBottom() {
    const container = $('#chatMessages');
    container.scrollTop = container.scrollHeight;
}

// ── 메시지 전송 ───────────────────────────────────────
const chatInput = $('#chatInput');
const sendBtn = $('#sendBtn');

chatInput.addEventListener('input', () => {
    sendBtn.disabled = !chatInput.value.trim();
    // 자동 높이 조정
    chatInput.style.height = 'auto';
    chatInput.style.height = Math.min(chatInput.scrollHeight, 150) + 'px';
});

chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

sendBtn.addEventListener('click', sendMessage);

async function sendMessage() {
    const message = chatInput.value.trim();
    if (!message) return;

    // 세션이 없으면 자동 생성
    if (!state.currentSessionId) {
        try {
            const data = await api('POST', '/sessions');
            if (!data) return;
            state.currentSessionId = data.session_id;
        } catch {
            showToast('세션 생성 실패', 'error');
            return;
        }
    }

    // 사용자 메시지 UI 표시
    const userIdx = state.messages.length;
    state.messages.push({ role: 'user', content: message, citations: [] });
    appendMessage('user', message);
    chatInput.value = '';
    chatInput.style.height = 'auto';
    sendBtn.disabled = true;

    // 타이핑 인디케이터 표시
    $('#typingIndicator').classList.add('active');

    try {
        const data = await api('POST', `/sessions/${state.currentSessionId}/chat`, { message });
        $('#typingIndicator').classList.remove('active');

        if (data) {
            const aiIdx = state.messages.length;
            state.messages.push({
                role: 'assistant',
                content: data.answer,
                citations: data.citations || [],
            });
            appendMessage('assistant', data.answer, data.citations, aiIdx);

            // 세션 목록 새로고침 (제목 업데이트 반영)
            await loadSessions();
        }
    } catch (err) {
        $('#typingIndicator').classList.remove('active');
        showToast('응답 생성 실패: ' + err.message, 'error');
    }
}

// ── 피드백 모달 ───────────────────────────────────────
function openFeedbackModal(messageIndex) {
    state.feedbackTargetIndex = messageIndex;
    $('#feedbackText').value = '';
    $('#feedbackModal').classList.add('active');
}

$('#feedbackCancel').addEventListener('click', () => {
    $('#feedbackModal').classList.remove('active');
});

$('#feedbackSubmit').addEventListener('click', async () => {
    const text = $('#feedbackText').value.trim();
    if (!text) {
        showToast('피드백 내용을 입력해주세요', 'error');
        return;
    }

    try {
        const data = await api('POST', '/feedback', {
            session_id: state.currentSessionId,
            message_index: state.feedbackTargetIndex,
            user_feedback: text,
        });

        if (data) {
            $('#feedbackModal').classList.remove('active');
            showToast(data.message || '피드백이 접수되었습니다', 'success');
        }
    } catch (err) {
        showToast('피드백 제출 실패: ' + err.message, 'error');
    }
});

// 모달 외부 클릭으로 닫기
$('#feedbackModal').addEventListener('click', (e) => {
    if (e.target.id === 'feedbackModal') {
        $('#feedbackModal').classList.remove('active');
    }
});

// ── 초기화 ────────────────────────────────────────────
(function init() {
    if (state.token && state.user) {
        showApp();
    } else {
        showLogin();
    }
})();
