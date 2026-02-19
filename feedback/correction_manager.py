"""
교정 데이터 관리 모듈
SQLite corrections 테이블 CRUD, 상태 전이, 교정 텍스트 파일 생성
"""
import uuid
from datetime import datetime, timezone
from pathlib import Path
from server.database import get_db
import config


def create_correction(
    session_id: str,
    submitted_by: str,
    original_question: str,
    ai_wrong_answer: str,
    user_correction: str,
    extracted_fact: str,
    confidence: float,
    correction_text: str,
) -> str:
    """신규 교정 데이터를 pending 상태로 저장. correction_id 반환."""
    correction_id = f"corr_{uuid.uuid4().hex[:8]}"
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO corrections
            (id, session_id, submitted_by, original_question, ai_wrong_answer,
             user_correction, extracted_fact, confidence, correction_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                correction_id, session_id, submitted_by,
                original_question, ai_wrong_answer, user_correction,
                extracted_fact, confidence, correction_text,
            ),
        )
        conn.commit()
        return correction_id
    finally:
        conn.close()


def list_corrections(status: str | None = None) -> list[dict]:
    """교정 목록 조회. status 필터 가능."""
    conn = get_db()
    try:
        if status:
            rows = conn.execute(
                """SELECT c.*, u.username as submitted_username 
                FROM corrections c JOIN users u ON c.submitted_by = u.id
                WHERE c.status = ? ORDER BY c.created_at DESC""",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT c.*, u.username as submitted_username
                FROM corrections c JOIN users u ON c.submitted_by = u.id
                ORDER BY c.created_at DESC""",
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_correction(correction_id: str) -> dict | None:
    """단일 교정 조회"""
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM corrections WHERE id = ?", (correction_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def approve_correction(correction_id: str, reviewed_by: str, store_doc_name: str = None) -> bool:
    """교정 승인 처리"""
    conn = get_db()
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """UPDATE corrections 
            SET status = 'approved', reviewed_by = ?, reviewed_at = ?, store_document_name = ?
            WHERE id = ? AND status = 'pending'""",
            (reviewed_by, now, store_doc_name, correction_id),
        )
        conn.commit()
        return conn.total_changes > 0
    finally:
        conn.close()


def reject_correction(correction_id: str, reviewed_by: str, reason: str) -> bool:
    """교정 거절 처리"""
    conn = get_db()
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """UPDATE corrections
            SET status = 'rejected', reviewed_by = ?, reviewed_at = ?, reject_reason = ?
            WHERE id = ? AND status = 'pending'""",
            (reviewed_by, now, reason, correction_id),
        )
        conn.commit()
        return conn.total_changes > 0
    finally:
        conn.close()


def save_correction_file(correction_id: str, correction_text: str) -> Path:
    """승인된 교정 텍스트를 파일로 저장 (Store 업로드용)"""
    file_path = config.CORRECTION_DOCS_DIR / f"{correction_id}.txt"
    file_path.write_text(correction_text, encoding="utf-8")
    return file_path


def get_stats() -> dict:
    """교정 상태별 통계"""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM corrections GROUP BY status"
        ).fetchall()
        stats = {r["status"]: r["cnt"] for r in rows}
        return {
            "pending": stats.get("pending", 0),
            "approved": stats.get("approved", 0),
            "rejected": stats.get("rejected", 0),
            "superseded": stats.get("superseded", 0),
            "total": sum(stats.values()),
        }
    finally:
        conn.close()
