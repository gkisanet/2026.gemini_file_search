# 📋 자가 수정형 사내 RAG 시스템

> **Gemini API File Search** 기반으로, 사내 규정·내부 자료에 대한 질문에 AI가 정확하게 답변하고,  
> 틀린 답변은 사용자 피드백과 관리자 승인을 거쳐 **자동으로 교정**되는 시스템입니다.

---

## 🎯 이 프로젝트는 무엇인가?

회사에는 인사규정, 출장규정, 복무규정 등 수많은 내부 문서가 있습니다.  
직원들이 "연차는 며칠인가요?" 같은 질문을 할 때, AI가 이 문서들을 읽어서 답변해줍니다.

하지만 AI가 틀린 답변을 할 수도 있습니다. 이때:

1. **사용자**가 "틀렸어, 정답은 이거야" 하고 피드백을 남기면
2. **AI(Gemini)**가 그 피드백을 분석해서 "어떤 질문에 / 뭘 틀렸고 / 정답은 뭔지" 추출하고
3. **관리자**가 검토 후 승인하면
4. 그 교정 내용이 **지식 베이스에 반영**되어, 이후 같은 질문에 올바르게 답합니다

이것이 **자가 수정형(Self-Correcting) RAG** 시스템입니다.

---

## 💡 핵심 개념 이해하기

### RAG (Retrieval Augmented Generation)란?

```
┌─────────────┐        ┌──────────────┐        ┌─────────────┐
│  사용자 질문  │───────▶│  문서 검색     │───────▶│  AI가 답변    │
│ "연차 며칠?"  │        │ (File Search) │        │ 생성 (Gemini) │
└─────────────┘        └──────────────┘        └─────────────┘
```

- **일반 AI**: 학습됐던 지식만으로 답변 → 최신 사규를 모름
- **RAG AI**: 질문이 오면 먼저 **관련 문서를 검색**해서 읽은 뒤 답변 → 정확도 향상

Gemini API의 **File Search 도구**가 이 "문서 검색" 부분을 자동으로 처리합니다.  
파일을 업로드하면 자동으로 **잘게 쪼개고(Chunking)** → **벡터로 변환(Embedding)** → **인덱싱**합니다.

### 왜 "자가 수정"이 필요한가?

AI는 대화 안에서만 "틀렸다"고 인지할 수 있습니다.  
**새로운 채팅**을 열면 과거 대화를 기억하지 못하기 때문에, 같은 실수를 반복합니다.

이를 해결하려면 AI가 읽는 **"참고 문서"를 업데이트**해야 합니다:

```
[교정 전]
AI가 읽는 문서: 사규.hwp (원본)

[교정 후]
AI가 읽는 문서: 사규.hwp (원본) + corr_abc123.txt (교정 데이터)
→ 시스템 프롬프트: "교정 데이터가 원본과 충돌하면 교정 데이터를 우선하라"
```

### 문서 버전 관리

동일한 규정이 매년 갱신되면, 날짜가 포함된 파일명으로 업로드합니다:

```
인사규정_20250101.hwp   ← 이전 버전 (is_latest = 0)
인사규정_20260101.hwp   ← 최신 버전 (is_latest = 1)  ★
```

시스템은 파일명의 **날짜 패턴을 자동 인식**하여:
- 같은 규정(version_group = "인사규정")으로 자동 그룹핑
- 최신 날짜 문서를 우선하여 검색·답변
- 이전 버전 내용도 함께 참고하여 **변경 이력**까지 안내

---

## 🏗️ 시스템 아키텍처

```
┌──────────────────────────────────────────────────────────────┐
│                     프론트엔드 (바닐라 JS)                      │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐    │
│  │  로그인 화면  │  │  채팅방 UI    │  │  관리자 대시보드    │    │
│  │  (JWT 인증)  │  │  (히스토리)   │  │  (교정·문서 관리)  │    │
│  └─────────────┘  └──────────────┘  └───────────────────┘    │
└──────────────────────────┬───────────────────────────────────┘
                           │ REST API
┌──────────────────────────┼───────────────────────────────────┐
│                    FastAPI 백엔드                              │
│  ┌──────────┐  ┌─────────┴──────────┐  ┌──────────────────┐  │
│  │ 세션/채팅  │  │   RAG 질의 엔진     │  │  피드백 루프       │  │
│  │  API      │  │ (이중 Store 검색)   │  │  (분석→저장→승인) │  │
│  └──────────┘  └─────────┬──────────┘  └──────────────────┘  │
└──────────────────────────┼───────────────────────────────────┘
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │  SQLite   │ │ Primary  │ │Correction│
        │  (사용자,  │ │  Store   │ │  Store   │
        │  세션,    │ │ (원본사규)│ │ (교정DB) │
        │  교정DB)  │ │          │ │          │
        └──────────┘ └──────────┘ └──────────┘
                     └─── Gemini File Search ───┘
```

### 이중 Store 전략

Gemini File Search에 **두 개의 Store**를 만들어 동시에 검색합니다:

| Store | 역할 | 업데이트 주기 |
|-------|------|-------------|
| **Primary Store** | 원본 사규·내부 자료 | 관리자가 수동 업로드 |
| **Correction Store** | 사용자 피드백으로 교정된 사실 | 승인 시 자동 업로드 |

AI에게는 시스템 프롬프트로 **"두 Store의 내용이 충돌하면 Correction Store 우선"** 이라고 지시합니다.

---

## 📁 프로젝트 구조

```
2026.gemini_file_search/
├── config.py                    # 환경 설정, 시스템 프롬프트
├── requirements.txt             # 의존성 패키지
├── .env.example                 # 환경변수 템플릿
│
├── core/                        # === 코어 RAG 엔진 ===
│   ├── store_manager.py         # File Search Store CRUD
│   ├── document_uploader.py     # 파일 업로드 (HWP 포함)
│   └── query_engine.py          # 이중 Store RAG 질의, Citation 파싱
│
├── feedback/                    # === 피드백 루프 ===
│   ├── feedback_analyzer.py     # Gemini가 피드백 분석 → 교정 데이터 추출
│   ├── correction_manager.py    # 교정 DB CRUD (pending → approved)
│   └── admin_review.py          # 승인 시 파일 생성 + Store 업로드 통합
│
├── server/                      # === 웹 서버 ===
│   ├── database.py              # SQLite 초기화 (users, sessions, corrections, documents)
│   ├── auth.py                  # JWT 인증 (admin/user 역할)
│   ├── routes.py                # REST API 엔드포인트 18개
│   └── app.py                   # FastAPI 앱 엔트리포인트
│
├── frontend/                    # === 웹 프론트엔드 ===
│   ├── index.html               # 메인 페이지 (로그인 + 채팅)
│   ├── admin.html               # 관리자 대시보드
│   ├── css/style.css            # 다크 모드 디자인 시스템
│   └── js/
│       ├── app.js               # 채팅 UI 로직
│       └── admin.js             # 관리자 대시보드 로직
│
├── data/                        # (자동 생성)
│   ├── rag_system.db            # SQLite 데이터베이스
│   └── corrections/             # 승인된 교정 텍스트 파일
│
├── primary_data/                # 원본 로우 데이터 (불변)
├── secondary_data/              # 전처리/유도된 데이터셋
├── intermediate_results/        # 분석 중간 결과물
├── visualizations/              # 생성된 이미지/차트 파일
├── interim_reports/             # 관리/분석 중간 보고서
├── scripts/                     # 분석 및 실행 스크립트
│
└── docs/                        # 문서
    ├── CONTEXT.md
    ├── TASKS.md
    ├── CHANGELOG.md
    └── HANDOVER.md
```

---

## 🔄 데이터 흐름 (전체 사이클)

### 1단계: 일반 질의 사이클

```
사용자 → "출장비 한도가 얼마인가요?"
          │
          ▼
    [FastAPI /api/sessions/{id}/chat]
          │
          ▼
    [query_engine.py]
    ├── 대화 히스토리 로드
    ├── Primary Store + Correction Store 동시 검색
    ├── Gemini가 문서 기반 답변 생성
    └── Citation(출처) 파싱
          │
          ▼
    사용자 ← "출장비 한도는 1일 30만원입니다. (출처: 출장규정 제5조)"
```

### 2단계: 피드백 교정 사이클

```
사용자 → "틀렸어! 올해부터 50만원으로 바뀌었어"
          │
          ▼
    [/api/feedback] → [feedback_analyzer.py]
    ├── Gemini가 피드백 분석
    │   "원래 질문: 출장비 한도?"
    │   "AI 오답: 30만원"
    │   "사용자 정답: 50만원"
    │   "교정 사실: 출장비 한도는 1일 50만원이다"
    └── corrections 테이블에 pending 상태로 저장
          │
          ▼
    관리자 대시보드에 교정 요청 표시
          │
          ▼
    관리자 → [승인 버튼 클릭]
    [/api/admin/feedbacks/{id}/approve] → [admin_review.py]
    ├── correction_data.txt 파일 생성
    ├── Correction Store에 업로드
    └── 이후 검색에 교정 데이터 반영
          │
          ▼
    (다음 사용자) → "출장비 한도가 얼마인가요?"
    AI ← "출장비 한도는 1일 50만원입니다. (기존 30만원에서 변경)"
```

---

## 🚀 시작하기

### 1. 환경 설정

```bash
# 프로젝트 디렉토리 이동
cd 2026.gemini_file_search

# 가상환경 생성 및 활성화
python3 -m venv .venv
source .venv/bin/activate

# 의존성 설치
pip install -r requirements.txt

# 환경변수 설정
cp .env.example .env
# .env 파일을 편집하여 Gemini API Key 입력
```

### 2. Gemini API Key 발급

1. [Google AI Studio](https://aistudio.google.com/) 접속
2. API Key 생성
3. `.env` 파일의 `GEMINI_API_KEY=여기에_입력`

### 3. 서버 실행

```bash
python3 -m server.app
# 또는
uvicorn server.app:app --host 0.0.0.0 --port 8000 --reload
```

### 4. 접속

- **채팅 UI**: http://localhost:8000
- **관리자 대시보드**: http://localhost:8000/admin

### 기본 계정

| 역할 | 아이디 | 비밀번호 |
|------|--------|---------|
| 관리자 | `admin` | `admin123` |
| 일반 사용자 | `user` | `user123` |

---

## 📖 기술 스택

| 구분 | 기술 | 용도 |
|------|------|------|
| **AI 엔진** | Gemini API (File Search) | RAG 질의, 피드백 분석 |
| **AI 모델** | Gemini 2.5 Flash | 빠르고 정확한 응답 생성 |
| **백엔드** | FastAPI (Python) | REST API 서버 |
| **인증** | JWT + bcrypt | 사용자 인증 및 역할 관리 |
| **데이터베이스** | SQLite (WAL 모드) | 세션, 교정, 문서 메타데이터 |
| **프론트엔드** | 바닐라 HTML/CSS/JS | 로그인, 채팅, 관리자 대시보드 |
| **디자인** | 다크 모드 + 글래스모피즘 | 모던 UI/UX |

---

## 🔑 핵심 API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/api/auth/login` | 로그인 → JWT 토큰 발급 |
| `GET` | `/api/sessions` | 채팅 세션 목록 |
| `POST` | `/api/sessions/{id}/chat` | 메시지 전송 + AI 응답 |
| `POST` | `/api/feedback` | 오답 피드백 제출 |
| `GET` | `/api/admin/feedbacks` | 교정 목록 (관리자) |
| `POST` | `/api/admin/feedbacks/{id}/approve` | 교정 승인 → Store 반영 |
| `GET` | `/api/admin/documents` | 문서 목록 (버전 그룹별) |
| `PUT` | `/api/admin/documents/{id}/set-latest` | 최신 버전 수동 지정 |
| `POST` | `/api/admin/upload` | 문서 업로드 |

---

## ⚙️ 환경 변수

| 변수명 | 설명 | 기본값 |
|--------|------|--------|
| `GEMINI_API_KEY` | Gemini API 키 | (필수) |
| `GEMINI_MODEL` | 사용할 모델명 | `gemini-2.5-flash` |
| `JWT_SECRET` | JWT 서명 키 | `change-me-in-production` |
| `DB_PATH` | SQLite 경로 | `data/rag_system.db` |
| `HOST` | 서버 호스트 | `0.0.0.0` |
| `PORT` | 서버 포트 | `8000` |
