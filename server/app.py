"""
FastAPI 애플리케이션 엔트리포인트
서버 시작, 정적 파일 서빙, DB 초기화
"""
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from server.database import init_db
from server.routes import router
import config

# FastAPI 앱 생성
app = FastAPI(
    title="사내 규정 RAG 시스템",
    description="Gemini File Search 기반 자가 수정형 사내 RAG",
    version="1.0.0",
)

# CORS 설정 (개발용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 라우트 등록
app.include_router(router)

# 프론트엔드 정적 파일 서빙
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
    app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")


@app.get("/")
def serve_index():
    """메인 페이지 (로그인 + 채팅 UI)"""
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/admin")
def serve_admin():
    """관리자 대시보드"""
    return FileResponse(FRONTEND_DIR / "admin.html")


@app.on_event("startup")
def startup():
    """서버 시작 시 DB 초기화"""
    init_db()
    print("✅ 데이터베이스 초기화 완료")
    print(f"🌐 서버: http://localhost:{config.PORT}")
    print(f"🔑 기본 계정: admin/admin123 (관리자), user/user123 (일반)")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.app:app", host=config.HOST, port=config.PORT, reload=True)
