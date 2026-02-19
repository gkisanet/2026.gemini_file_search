"""
전역 설정 모듈
.env 파일에서 환경변수를 읽어 상수로 관리한다.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 프로젝트 루트 경로
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "app.db"
CORRECTION_DOCS_DIR = DATA_DIR / "correction_docs"

# .env 로딩
load_dotenv(BASE_DIR / ".env")

# Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

# JWT 인증
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-this-secret-key")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))

# 교정 모드: "auto" 또는 "manual"
CORRECTION_MODE = os.getenv("CORRECTION_MODE", "manual")

# 서버
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# File Search Store 이름 (런타임에 설정됨)
PRIMARY_STORE_DISPLAY_NAME = "사내규정-원본"
CORRECTION_STORE_DISPLAY_NAME = "사내규정-교정"

# 시스템 프롬프트 — 교정 데이터 우선순위 규칙
SYSTEM_PROMPT = """당신은 사내 규정 전문가 AI 어시스턴트입니다.

[핵심 규칙]
1. 반드시 제공된 문서(사규)를 근거로 답변하세요.
2. 원본 사규와 교정 데이터(correction_data)의 내용이 충돌할 경우,
   교정 데이터의 내용을 최우선 정답으로 삼으세요.
3. 교정 데이터에는 과거 오답을 수정한 검증된 정보가 포함되어 있습니다.
4. 답변 시 출처(문서명, 조항 번호 등)를 명시하세요.
5. 문서에서 답을 찾을 수 없으면 솔직하게 "해당 내용을 찾을 수 없습니다"라고 답하세요.
6. 한국어로 답변하세요.

[문서 버전 관리 규칙]
- 동일한 규정에 대해 파일명에 날짜가 포함된 여러 버전이 존재할 수 있습니다.
  (예: 인사규정_20250101.hwp, 인사규정_20260101.hwp)
- 파일명의 날짜(YYYYMMDD, YYYY-MM-DD, YYYY.MM.DD 등)를 인식하여
  **가장 최신 날짜의 문서 내용을 최우선 기준**으로 답변하세요.
- 이전 버전의 내용도 참고하여, 규정이 어떻게 변경되었는지 변화 이력을
  함께 안내해주면 더 좋습니다. 예: "기존 규정(2025년)에서는 15일이었으나,
  최신 규정(2026년)에서 16일로 변경되었습니다."
- 날짜가 없는 문서와 날짜가 있는 문서가 충돌하면, 날짜가 있는 최신 문서를 우선합니다.
"""

# 디렉토리 자동 생성
DATA_DIR.mkdir(exist_ok=True)
CORRECTION_DOCS_DIR.mkdir(parents=True, exist_ok=True)
