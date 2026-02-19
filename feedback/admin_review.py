"""
관리자 승인 워크플로우
교정 승인 시 교정 Store에 자동 업로드하는 통합 처리
"""
from feedback.correction_manager import (
    approve_correction,
    reject_correction,
    get_correction,
    save_correction_file,
)
from core.document_uploader import upload_file
from core.store_manager import get_or_create_store
import config


def process_approval(correction_id: str, reviewed_by: str) -> dict:
    """
    교정 승인 전체 흐름:
    1. corrections 테이블 상태를 approved로 변경
    2. 교정 텍스트를 파일로 저장
    3. 교정 File Search Store에 업로드
    """
    correction = get_correction(correction_id)
    if not correction:
        return {"success": False, "error": "교정 데이터를 찾을 수 없습니다"}

    if correction["status"] != "pending":
        return {"success": False, "error": f"이미 처리된 교정입니다 (상태: {correction['status']})"}

    # 교정 텍스트 파일 생성
    file_path = save_correction_file(correction_id, correction["correction_text"])

    # 교정 Store에 업로드
    store_name = get_or_create_store(config.CORRECTION_STORE_DISPLAY_NAME)
    upload_result = upload_file(file_path, store_name)

    if not upload_result["success"]:
        return {"success": False, "error": f"Store 업로드 실패: {upload_result['error']}"}

    # DB 상태 변경
    approve_correction(correction_id, reviewed_by, store_doc_name=store_name)

    return {
        "success": True,
        "correction_id": correction_id,
        "message": "교정이 승인되어 지식 베이스에 반영되었습니다",
    }


def process_rejection(correction_id: str, reviewed_by: str, reason: str) -> dict:
    """교정 거절 처리"""
    correction = get_correction(correction_id)
    if not correction:
        return {"success": False, "error": "교정 데이터를 찾을 수 없습니다"}

    if correction["status"] != "pending":
        return {"success": False, "error": f"이미 처리된 교정입니다 (상태: {correction['status']})"}

    if not reason.strip():
        return {"success": False, "error": "거절 사유를 입력해주세요"}

    reject_correction(correction_id, reviewed_by, reason)

    return {
        "success": True,
        "correction_id": correction_id,
        "message": "교정이 거절되었습니다",
    }
