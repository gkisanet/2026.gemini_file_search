"""
문서 업로드 및 인덱싱 모듈
HWP, PDF, DOCX 등 파일을 File Search Store에 업로드하고 인덱싱 완료를 대기
"""
import time
from pathlib import Path
from google import genai
import config

# 지원 확장자 → MIME 타입 매핑
MIME_MAP = {
    ".hwp": "application/x-hwp",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".txt": "text/plain",
    ".json": "application/json",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".md": "text/markdown",
    ".csv": "text/csv",
}

# 최대 폴링 대기 시간(초)
MAX_POLL_SECONDS = 300
POLL_INTERVAL = 5


def _get_client() -> genai.Client:
    return genai.Client(api_key=config.GEMINI_API_KEY)


def upload_file(file_path: str | Path, store_name: str) -> dict:
    """
    단일 파일을 File Search Store에 업로드하고 인덱싱 완료까지 대기.
    반환: {"success": bool, "file": str, "error": str | None}
    """
    file_path = Path(file_path)

    if not file_path.exists():
        return {"success": False, "file": str(file_path), "error": "파일이 존재하지 않습니다"}

    ext = file_path.suffix.lower()
    if ext not in MIME_MAP:
        return {"success": False, "file": str(file_path), "error": f"지원하지 않는 파일 형식: {ext}"}

    client = _get_client()

    try:
        # Store에 직접 업로드
        operation = client.file_search_stores.upload_to_file_search_store(
            file=str(file_path),
            file_search_store_name=store_name,
            config={"display_name": file_path.name},
        )

        # 인덱싱 완료 대기
        elapsed = 0
        while not operation.done and elapsed < MAX_POLL_SECONDS:
            time.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL
            operation = client.operations.get(operation)

        if not operation.done:
            return {"success": False, "file": str(file_path), "error": "인덱싱 타임아웃"}

        return {"success": True, "file": str(file_path), "error": None}

    except Exception as e:
        return {"success": False, "file": str(file_path), "error": str(e)}


def upload_directory(dir_path: str | Path, store_name: str) -> list[dict]:
    """
    디렉토리 내 모든 지원 파일을 업로드.
    반환: 각 파일의 업로드 결과 리스트
    """
    dir_path = Path(dir_path)
    results = []

    if not dir_path.is_dir():
        return [{"success": False, "file": str(dir_path), "error": "디렉토리가 아닙니다"}]

    for f in sorted(dir_path.iterdir()):
        if f.is_file() and f.suffix.lower() in MIME_MAP:
            result = upload_file(f, store_name)
            results.append(result)

    return results
