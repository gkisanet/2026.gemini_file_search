# 🤝 HANDOVER — 세션 인수인계

## 현재 상태
- 전체 시스템 코드 구현 완료 (백엔드 + 프론트엔드)
- GitHub 리포지토리 push 완료: `gkisanet/2026.gemini_file_search`
- 서버 실행 및 UI 검증 진행 중

## 즉시 실행 가능 환경
```bash
cd ~/topProject/2026.gemini_file_search
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # GEMINI_API_KEY 입력
python3 -m server.app
```

## Next Steps
1. **서버 실행 검증** — `python3 -m server.app`으로 서버 띄우고 브라우저에서 확인
2. **실제 문서 업로드 테스트** — HWP/PDF 사규 파일을 관리자 대시보드에서 업로드
3. **피드백 루프 테스트** — 채팅에서 오답 피드백 → 관리자 승인 → 교정 반영 확인
4. **프로덕션 배포** — Docker 컨테이너화 또는 Cloud Run 배포 고려

## 핵심 파일
- `config.py` — 모든 설정의 중심 (API키, 모델, 프롬프트)
- `server/routes.py` — 전체 API 엔드포인트 정의
- `core/query_engine.py` — RAG 질의 핵심 로직
- `feedback/admin_review.py` — 교정 승인 → Store 업로드 통합 워크플로우
