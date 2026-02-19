# 📜 CHANGELOG

## [2026-02-20] 초기 구축 — 전체 시스템 구현

### 추가
- **코어 엔진**: `store_manager.py`, `document_uploader.py`, `query_engine.py` (core/)
- **피드백 루프**: `feedback_analyzer.py`, `correction_manager.py`, `admin_review.py` (feedback/)
- **웹 서버**: `database.py`, `auth.py`, `routes.py`, `app.py` (server/)
- **프론트엔드**: `index.html`, `admin.html`, `style.css`, `app.js`, `admin.js` (frontend/)
- **문서 버전 관리**: `documents` 테이블, 날짜 자동 파싱, 최신 버전 관리 API
- **설정**: `config.py`, `.env.example`, `requirements.txt`, `.gitignore`
- **문서화**: `README.md`, `docs/` (CONTEXT, TASKS, CHANGELOG, HANDOVER)
