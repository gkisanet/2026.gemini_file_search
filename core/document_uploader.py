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
    한글 파일명 등 non-ASCII 경로 대응: 임시 ASCII 심링크 생성 후 업로드.
    반환: {"success": bool, "file": str, "error": str | None}
    """
    import uuid
    import shutil
    import tempfile

    file_path = Path(file_path)

    if not file_path.exists():
        return {"success": False, "file": str(file_path), "error": "파일이 존재하지 않습니다"}

    ext = file_path.suffix.lower()
    if ext not in MIME_MAP:
        return {"success": False, "file": str(file_path), "error": f"지원하지 않는 파일 형식: {ext}"}

    client = _get_client()
    original_name = file_path.name  # 원본 파일명 (한글 포함 가능)

    # non-ASCII 파일 경로 여부 확인 → 임시 ASCII 경로로 복사
    temp_copy_path = None
    upload_path = file_path
    try:
        str(file_path).encode("ascii")
    except UnicodeEncodeError:
        # ASCII 인코딩 불가 → 임시 디렉터리에 UUID 기반 ASCII 이름으로 복사
        temp_dir = tempfile.mkdtemp()
        safe_name = f"{uuid.uuid4().hex}{ext}"
        temp_copy_path = Path(temp_dir) / safe_name
        shutil.copy2(file_path, temp_copy_path)
        upload_path = temp_copy_path

    try:
        # Store에 업로드 (ASCII-safe 경로 사용, display_name은 원본 한글명 유지)
        operation = client.file_search_stores.upload_to_file_search_store(
            file=str(upload_path),
            file_search_store_name=store_name,
            config={"display_name": original_name},
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
    finally:
        # 임시 복사본 정리
        if temp_copy_path and temp_copy_path.exists():
            shutil.rmtree(temp_copy_path.parent, ignore_errors=True)


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
