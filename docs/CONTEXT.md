# 🧠 CONTEXT — 아키텍처 및 설계 의도

## 시스템 개요

Gemini API File Search 기반 **자가 수정형 사내 RAG** 시스템.  
사용자 피드백 → Gemini 분석 → 관리자 승인 → 지식 베이스 자동 반영.

## 핵심 설계 결정

### 1. 이중 Store 전략
- **Primary Store**: 원본 사규 → 관리자 수동 업로드
- **Correction Store**: 교정 사실 → 승인 시 자동 업로드
- 시스템 프롬프트로 **교정 데이터 우선** 지시

### 2. Human-in-the-Loop
- 사용자 피드백이 바로 반영되지 않고 **관리자 검토 후 승인** 필수
- 지식 오염 방지 목적

### 3. 문서 버전 관리
- 파일명 날짜 패턴 자동 파싱 (`인사규정_20260101.hwp`)
- `version_group`으로 동일 규정 그룹핑, `is_latest` 플래그로 최신 관리
- AI 프롬프트에서 최신 날짜 문서 우선 답변 지시

### 4. 모델 선택
- **Gemini 2.5 Flash Lite**: File Search 지원, 비용 효율적, Q&A에 충분한 성능

## 데이터 흐름

```
[사용자] → POST /api/sessions/{id}/chat
  → query_engine.py → Gemini File Search (Primary + Correction Store 동시)
  → 응답 + Citations 반환

[피드백] → POST /api/feedback
  → feedback_analyzer.py → Gemini로 분석 → corrections 테이블 (pending)

[관리자 승인] → POST /api/admin/feedbacks/{id}/approve
  → admin_review.py → correction_text 파일 생성 → Correction Store 업로드
```

## DB 스키마 (SQLite)

| 테이블 | 역할 |
|--------|------|
| `users` | 사용자 계정 (admin/user) |
| `sessions` | 채팅 세션 |
| `messages` | 대화 메시지 (role, content, citations) |
| `corrections` | 교정 데이터 (pending/approved/rejected) |
| `documents` | 업로드 문서 메타데이터 (버전 관리) |
