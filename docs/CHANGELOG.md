# 📜 CHANGELOG

## [2026-02-20] 초기 구축 — 전체 시스템 구현

### 추가
- **코어 엔진**: `store_manager.py`, `document_uploader.py`, `query_engine.py` (core/)
- **피드백 루프**: `feedback_analyzer.py`, `correction_manager.py`, `admin_review.py` (feedback/)
- **웹 서버**: `database.py`, `auth.py`, `routes.py`, `app.py` (server/)
- **프론트엔드**: `index.html`, `admin.html`, `style.css`, `app.js`, `admin.js` (frontend/)
- **문서 버전 관리**: `documents` 테이블, 날짜 자동 파싱, 최신 버전 관리 API
- **설정**: `config.py`, `.env.example`, `requirements.txt`, `.gitignore`
- **데이터 파이프라인**: `primary_data`, `secondary_data`, `intermediate_results`, `visualizations`, `interim_reports`, `scripts` 구조 추가
- **치명적 버그 수정**: `database.py`의 `DROP TABLE IF EXISTS documents` 제거 — 서버 재시작 시 업로드된 문서 메타데이터가 모두 사라지던 문제 해결
- **업로드 오류 가시성 개선**: 업로드 실패 시 서버 로그 및 토스트 메시지에 실패 사유를 상세히 표시하도록 개선
- **문서 메타데이터 고도화**: `olefile` 기반 HWP 고유 생성/수정시간 직접 파싱 기능 적용, PDF/XLSX 일괄 업로드 지원 및 `os.stat` fallback 적용
- **LLM 자동 분류**: `admin_upload` 라우터에 Gemini API를 결합하여 파일명 기반으로 [인사, 재무, 복무, 기획, 보안, 시스템, 기타] 카테고리 자동 유추·DB 삽입 기능 추가
- **UI/UX 개선**: 관리자 업로드 페이지에서 서버 내부 경로 텍스트박스 외에도, **운영체제 전용 📁 폴더 선택기 및 📄 파일 선택기**를 브라우저에 직접 띄워 클라이언트 직통(Multipart FormData)으로 대량 업로드하는 기능(`upload_client` 엔드포인트) 탑재
- **DB 스키마 확장**: 통계 및 LLM 카테고리 태깅을 위한 `doc_created_at`, `doc_modified_at`, `file_size`, `category` 컬럼 `documents` 테이블에 추가 (`server/database.py` 갱신 완료)
- **문서화**: `README.md`, `docs/` (CONTEXT, TASKS, CHANGELOG, HANDOVER)
