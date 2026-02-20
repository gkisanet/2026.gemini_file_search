"""
FastAPI API 라우트
인증, 세션/채팅, 피드백, 관리 API 전체 정의
"""
import json
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import List
import shutil
import tempfile
import os
import olefile
import re
from pathlib import Path
from server.auth import (
    authenticate_user, create_access_token,
    get_current_user, require_admin,
)
from server.database import get_db
from core.query_engine import query, generate_session_title
from core.store_manager import get_or_create_store, list_stores, get_store_documents
from core.document_uploader import upload_file as upload_doc, upload_directory
from feedback.feedback_analyzer import analyze_feedback, generate_correction_text
from feedback.correction_manager import (
    create_correction, list_corrections, get_stats,
)
from feedback.admin_review import process_approval, process_rejection
import config

router = APIRouter(prefix="/api")


# ── Pydantic 모델 ──────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

class ChatRequest(BaseModel):
    message: str

class FeedbackRequest(BaseModel):
    session_id: str
    message_index: int  # 피드백 대상 AI 메시지 인덱스
    user_feedback: str

class RejectRequest(BaseModel):
    reason: str

class UploadRequest(BaseModel):
    path: str  # 파일 또는 디렉토리 경로
    store_type: str = "primary"  # "primary" 또는 "correction"
    version_group: str = ""  # 기존 문서 그룹명 (신규 버전 연결 시)


# ── 인증 API ───────────────────────────────────────────

@router.post("/auth/login")
def login(req: LoginRequest):
    """로그인 → JWT 토큰 발급"""
    user = authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다")
    token = create_access_token(user["user_id"], user["username"], user["role"])
    return {"token": token, "user": user}


# ── 세션 API ───────────────────────────────────────────

@router.get("/sessions")
def get_sessions(current_user: dict = Depends(get_current_user)):
    """현재 사용자의 세션 목록 (최신순)"""
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT id, title, created_at, updated_at FROM sessions
            WHERE user_id = ? ORDER BY updated_at DESC""",
            (current_user["user_id"],),
        ).fetchall()
        return {"sessions": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.post("/sessions")
def create_session(current_user: dict = Depends(get_current_user)):
    """새 채팅 세션 생성"""
    session_id = f"sess_{uuid.uuid4().hex[:12]}"
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO sessions (id, user_id, title) VALUES (?, ?, ?)",
            (session_id, current_user["user_id"], "새 대화"),
        )
        conn.commit()
        return {"session_id": session_id}
    finally:
        conn.close()


@router.get("/sessions/{session_id}")
def get_session(session_id: str, current_user: dict = Depends(get_current_user)):
    """특정 세션의 메시지 전체 로드"""
    conn = get_db()
    try:
        # 세션 소유권 확인
        session = conn.execute(
            "SELECT * FROM sessions WHERE id = ? AND user_id = ?",
            (session_id, current_user["user_id"]),
        ).fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")

        messages = conn.execute(
            "SELECT role, content, citations, created_at FROM messages WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        ).fetchall()

        return {
            "session": dict(session),
            "messages": [
                {**dict(m), "citations": json.loads(m["citations"]) if m["citations"] else []}
                for m in messages
            ],
        }
    finally:
        conn.close()


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, current_user: dict = Depends(get_current_user)):
    """세션 삭제"""
    conn = get_db()
    try:
        conn.execute(
            "DELETE FROM sessions WHERE id = ? AND user_id = ?",
            (session_id, current_user["user_id"]),
        )
        conn.commit()
        return {"message": "세션이 삭제되었습니다"}
    finally:
        conn.close()


# ── 채팅 API ───────────────────────────────────────────

@router.post("/sessions/{session_id}/chat")
def chat(session_id: str, req: ChatRequest, current_user: dict = Depends(get_current_user)):
    """메시지 전송 + AI 응답"""
    conn = get_db()
    try:
        # 세션 소유권 확인
        session = conn.execute(
            "SELECT * FROM sessions WHERE id = ? AND user_id = ?",
            (session_id, current_user["user_id"]),
        ).fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")

        # 대화 히스토리 로드
        history_rows = conn.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        ).fetchall()
        history = [{"role": r["role"], "content": r["content"]} for r in history_rows]

        # 사용자 메시지 저장
        conn.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (?, 'user', ?)",
            (session_id, req.message),
        )

        # RAG 질의 수행
        result = query(message=req.message, history=history)

        # AI 응답 저장
        citations_json = json.dumps(result["citations"], ensure_ascii=False) if result["citations"] else None
        conn.execute(
            "INSERT INTO messages (session_id, role, content, citations) VALUES (?, 'assistant', ?, ?)",
            (session_id, result["answer"], citations_json),
        )

        # 첫 메시지면 세션 제목 자동 생성
        if not history:
            title = generate_session_title(req.message)
            conn.execute(
                "UPDATE sessions SET title = ? WHERE id = ?",
                (title, session_id),
            )

        # 세션 updated_at 갱신
        conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), session_id),
        )

        conn.commit()

        return {
            "answer": result["answer"],
            "citations": result["citations"],
            "model": result["model"],
        }
    finally:
        conn.close()


# ── 피드백 API ─────────────────────────────────────────

@router.post("/feedback")
def submit_feedback(req: FeedbackRequest, current_user: dict = Depends(get_current_user)):
    """사용자 피드백 제출 → Gemini 분석 → pending 상태로 저장"""
    conn = get_db()
    try:
        # 세션에서 원본 Q&A 추출
        messages = conn.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY created_at",
            (req.session_id,),
        ).fetchall()

        if req.message_index >= len(messages):
            raise HTTPException(status_code=400, detail="유효하지 않은 메시지 인덱스입니다")

        # 피드백 대상 AI 메시지와 그 직전 사용자 메시지 찾기
        ai_msg = messages[req.message_index]
        # 직전 사용자 메시지 찾기
        original_question = ""
        for i in range(req.message_index - 1, -1, -1):
            if messages[i]["role"] == "user":
                original_question = messages[i]["content"]
                break

        # Gemini로 피드백 분석
        analysis = analyze_feedback(
            original_question=original_question,
            ai_answer=ai_msg["content"],
            user_feedback=req.user_feedback,
        )

        if not analysis:
            raise HTTPException(status_code=500, detail="피드백 분석에 실패했습니다")

        # 교정 텍스트 생성
        correction_text = generate_correction_text(analysis)

        # DB에 pending 상태로 저장
        correction_id = create_correction(
            session_id=req.session_id,
            submitted_by=current_user["user_id"],
            original_question=analysis["original_question"],
            ai_wrong_answer=analysis["ai_wrong_answer"],
            user_correction=analysis["user_correction"],
            extracted_fact=analysis["extracted_fact"],
            confidence=analysis.get("confidence", 0.5),
            correction_text=correction_text,
        )

        return {
            "correction_id": correction_id,
            "message": "피드백이 접수되었습니다. 관리자 검토 후 지식 베이스에 반영됩니다.",
            "analysis": analysis,
        }
    finally:
        conn.close()


# ── 관리 API (admin only) ─────────────────────────────

@router.get("/admin/feedbacks")
def admin_list_feedbacks(status: str = None, admin: dict = Depends(require_admin)):
    """교정 피드백 목록 조회 (필터 가능)"""
    corrections = list_corrections(status=status)
    stats = get_stats()
    return {"corrections": corrections, "stats": stats}


@router.post("/admin/feedbacks/{correction_id}/approve")
def admin_approve(correction_id: str, admin: dict = Depends(require_admin)):
    """교정 승인 → Store 업로드"""
    result = process_approval(correction_id, admin["user_id"])
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/admin/feedbacks/{correction_id}/reject")
def admin_reject(correction_id: str, req: RejectRequest, admin: dict = Depends(require_admin)):
    """교정 거절 (사유 필수)"""
    result = process_rejection(correction_id, admin["user_id"], req.reason)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/admin/stores")
def admin_stores(admin: dict = Depends(require_admin)):
    """File Search Store 현황"""
    stores = list_stores()
    store_details = []
    for s in stores:
        docs = get_store_documents(s["name"])
        store_details.append({**s, "document_count": len(docs), "documents": docs})
    return {"stores": store_details}


@router.get("/admin/store_files")
def admin_store_files(
    page: int = 1,
    limit: int = 20,
    search: str = "",
    category: str = "",
    store_type: str = "",
    admin: dict = Depends(require_admin),
):
    """DB 기반 Store 파일 목록 — 페이지네이션, 검색, 필터 지원"""
    conn = get_db()
    
    # 동적 WHERE 절 구성
    conditions = []
    params = []
    
    if search.strip():
        conditions.append("(file_name LIKE ? OR version_group LIKE ?)")
        search_term = f"%{search.strip()}%"
        params.extend([search_term, search_term])
    
    if category.strip():
        conditions.append("category = ?")
        params.append(category.strip())
    
    if store_type.strip():
        conditions.append("store_type = ?")
        params.append(store_type.strip())
    
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    
    # 총 개수 조회
    total = conn.execute(
        f"SELECT count(*) FROM documents {where_clause}", params
    ).fetchone()[0]
    
    # 페이지네이션 적용
    offset = (page - 1) * limit
    rows = conn.execute(
        f"""SELECT id, file_name, display_name, version_group, version_date,
                   is_latest, store_type, category, file_size,
                   doc_created_at, doc_modified_at, created_at
            FROM documents {where_clause}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?""",
        params + [limit, offset],
    ).fetchall()
    
    conn.close()
    
    files = [dict(r) for r in rows]
    total_pages = max(1, (total + limit - 1) // limit)
    
    # 카테고리 별 통계 (필터 UI용)
    conn2 = get_db()
    cat_stats = conn2.execute(
        "SELECT category, count(*) as cnt FROM documents GROUP BY category ORDER BY cnt DESC"
    ).fetchall()
    conn2.close()
    
    return {
        "files": files,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "categories": [{"name": r["category"] or "미분류", "count": r["cnt"]} for r in cat_stats],
    }


def _extract_metadata_and_group(filename: str) -> dict:
    """
    파일명과 파일 속성/내부 메타데이터에서 정보를 추출.
    반환: {
        "version_group": str,
        "version_date": str,
        "doc_created_at": datetime,
        "doc_modified_at": datetime,
        "file_size": int
    }
    """
    file_path = Path(filename)
    stem = file_path.stem
    
    meta = {
        "version_group": stem,
        "version_date": "",
        "doc_created_at": None,
        "doc_modified_at": None,
        "file_size": 0
    }

    # 1. 파일명에서 version_group 추출 (숫자와 구분자 제거)
    group = re.sub(r'[-_.]?\d{4}[-_.]?\d{2}[-_.]?\d{2}[-_.]?', '', stem).strip('_.- ')
    if group:
        meta["version_group"] = group
    
    # 파일이 로컬에 실제로 존재하는지 확인
    if not file_path.exists():
        return meta
        
    # 2. 파일 크기 및 기본 OS 시간 추출 (Fallback)
    stat = os.stat(file_path)
    meta["file_size"] = stat.st_size
    meta["doc_modified_at"] = datetime.fromtimestamp(stat.st_mtime)
    meta["doc_created_at"] = datetime.fromtimestamp(stat.st_ctime)
    
    # OS 시간 중 최신 날짜를 기본 version_date 후보로 설정
    best_dt = max(meta["doc_modified_at"], meta["doc_created_at"])

    # 3. HWP 파일인 경우 OLE 내부 메타데이터 추출 우선 적용
    if file_path.suffix.lower() == ".hwp" and olefile.isOleFile(file_path):
        try:
            with olefile.OleFileIO(file_path) as ole:
                # \x05는 SummaryInformation 스트림의 시작 문자
                if ole.exists("\x05HwpSummaryInformation"):
                    props = ole.getproperties("\x05HwpSummaryInformation")
                    
                    # 속성 ID 12 (Create Time)
                    if 12 in props and isinstance(props[12], datetime):
                        meta["doc_created_at"] = props[12]
                        best_dt = props[12]
                        
                    # 속성 ID 13 (Last Save Time)
                    if 13 in props and isinstance(props[13], datetime):
                        meta["doc_modified_at"] = props[13]
                        if props[13] > best_dt:
                            best_dt = props[13]
        except Exception as e:
            print(f"HWP 메타데이터 추출 실패 ({filename}): {e}")
            
    # 최종 결정된 날짜로 version_date 생성 (YYYYMMDD)
    meta["version_date"] = best_dt.strftime("%Y%m%d")
    
    # 파일명 자체에 명시적 날짜 패턴이 있다면 그것을 version_date로 우선 시도 고려(기존 동작 유지성격)
    m = re.search(r'(\d{4})[-_.]?(\d{2})[-_.]?(\d{2})', stem)
    if m:
        meta["version_date"] = f"{m.group(1)}{m.group(2)}{m.group(3)}"

    return meta

# 카테고리 분류 Rate Limit 대응을 위한 딜레이 상수 (초)
CATEGORY_PREDICT_DELAY = 3  # 분당 20회 제한 준수용
CATEGORY_MAX_RETRIES = 3    # 429 에러 시 최대 재시도 횟수

def _predict_category(filename: str) -> str:
    """Gemini를 사용하여 파일명 기반 카테고리 1개 추출 (Rate Limit 자동 재시도)"""
    import time as _time
    from google import genai
    
    # Rate Limit 준수를 위한 딜레이
    _time.sleep(CATEGORY_PREDICT_DELAY)
    
    for attempt in range(CATEGORY_MAX_RETRIES):
        try:
            client = genai.Client(api_key=config.GEMINI_API_KEY)
            stem = Path(filename).stem
            prompt = f"다음 파일명을 보고 [인사, 재무, 복무, 기획, 보안, 시스템, 기타] 중 하나의 카테고리로 가장 적절한 단어 1개만 반환해. 부가 설명 절대 금지.\n파일명: {stem}"
            response = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=prompt
            )
            cat = response.text.strip().replace("'", "").replace('"', '').replace('\n', '')
            valid_categories = ['인사', '재무', '복무', '기획', '보안', '시스템', '기타']
            
            for valid in valid_categories:
                if valid in cat:
                    return valid
            return '기타'
        except Exception as e:
            err_str = str(e)
            # 429 Rate Limit → 대기 후 재시도
            if '429' in err_str or 'RESOURCE_EXHAUSTED' in err_str:
                wait_sec = 60  # 기본 대기
                # API 응답에서 retryDelay 추출 시도
                import re as _re
                m = _re.search(r'retryDelay.*?(\d+)', err_str)
                if m:
                    wait_sec = int(m.group(1)) + 5
                print(f"⏳ Rate Limit 도달 ({filename}) — {wait_sec}초 대기 후 재시도 ({attempt+1}/{CATEGORY_MAX_RETRIES})")
                _time.sleep(wait_sec)
                continue
            # 그 외 에러는 포기
            print(f"카테고리 분류 실패 ({filename}): {e}")
            return '기타'
    
    print(f"카테고리 분류 포기 ({filename}): Rate Limit 재시도 횟수 초과")
    return '기타'


@router.post("/admin/upload")
def admin_upload(req: UploadRequest, admin: dict = Depends(require_admin)):
    """문서 업로드 (원본 또는 교정 Store) + 문서 메타데이터 등록"""
    import re

    display_name = (
        config.PRIMARY_STORE_DISPLAY_NAME if req.store_type == "primary"
        else config.CORRECTION_STORE_DISPLAY_NAME
    )
    store_name = get_or_create_store(display_name)

    from pathlib import Path
    path = Path(req.path)

    if path.is_dir():
        results = upload_directory(path, store_name)
    elif path.is_file():
        results = [upload_doc(path, store_name)]
    else:
        raise HTTPException(status_code=400, detail="유효하지 않은 경로입니다")

    conn = get_db()
    try:
        for r in results:
            if not r["success"]:
                continue
            fname = r["file"]
            
            # 중복 방지: 같은 파일명이 이미 DB에 있으면 스킵
            existing = conn.execute(
                "SELECT id FROM documents WHERE file_name = ? AND store_type = ?",
                (fname, req.store_type)
            ).fetchone()
            if existing:
                print(f"⏭️ 중복 스킵 [{fname}]: 이미 DB에 존재")
                continue
                
            meta = _extract_metadata_and_group(fname)
            
            # 사용자가 version_group을 명시했으면 그것을 사용
            version_group = req.version_group.strip() if req.version_group.strip() else meta["version_group"]
            version_date = meta["version_date"]
            doc_id = f"doc_{uuid.uuid4().hex[:8]}"

            # AI 카테고리 자동 유추 (실패해도 업로드는 계속 진행)
            try:
                category = _predict_category(fname)
            except Exception:
                category = None

            # 같은 version_group의 기존 문서를 is_latest=0으로 갱신
            conn.execute(
                "UPDATE documents SET is_latest = 0 WHERE version_group = ? AND store_type = ?",
                (version_group, req.store_type),
            )

            # 새 문서 메타데이터 등록 (확장된 컬럼 포함)
            conn.execute(
                """INSERT INTO documents
                (id, file_name, display_name, version_group, version_date,
                 is_latest, store_name, store_type, 
                 doc_created_at, doc_modified_at, file_size, category,
                 uploaded_by)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?)""",
                (doc_id, fname, fname, version_group, version_date,
                 store_name, req.store_type, 
                 meta["doc_created_at"].isoformat() if meta["doc_created_at"] else None,
                 meta["doc_modified_at"].isoformat() if meta["doc_modified_at"] else None,
                 meta["file_size"],
                 category,
                 admin["user_id"]),
            )
        conn.commit()
    finally:
        conn.close()

    success_count = sum(1 for r in results if r["success"])
    return {
        "message": f"{success_count}/{len(results)}개 파일 업로드 완료",
        "results": results,
    }


@router.post("/admin/upload_client")
def admin_upload_client(
    files: List[UploadFile] = File(...),
    store_type: str = Form("primary"),
    version_group: str = Form(""),
    admin: dict = Depends(require_admin)
):
    """클라이언트 브라우저에서 폴더/파일 선택으로 업로드 처리"""
    from core.document_uploader import MIME_MAP
    
    display_name = (
        config.PRIMARY_STORE_DISPLAY_NAME if store_type == "primary"
        else config.CORRECTION_STORE_DISPLAY_NAME
    )
    store_name = get_or_create_store(display_name)
    
    conn = get_db()
    results = []
    
    with tempfile.TemporaryDirectory() as temp_dir:
        for f in files:
            temp_path = Path(temp_dir) / f.filename
            # 서브 디렉토리 구조 유지
            temp_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(temp_path, "wb") as buffer:
                shutil.copyfileobj(f.file, buffer)
            
            # 지원 파일 확인 (소문자로 확장자 검사)
            if temp_path.suffix.lower() not in MIME_MAP:
                results.append({"success": False, "file": f.filename, "error": "지원하지 않는 확장자"})
                continue
            
            # 중복 방지: 같은 파일명이 이미 DB에 있으면 스킵
            existing = conn.execute(
                "SELECT id FROM documents WHERE file_name = ? AND store_type = ?",
                (f.filename, store_type)
            ).fetchone()
            if existing:
                print(f"⏭️ 중복 스킵 [{f.filename}]: 이미 DB에 존재")
                results.append({"success": True, "file": f.filename, "error": "중복 스킵"})
                continue
                
            # File search API 업로드
            res = upload_doc(temp_path, store_name)
            # 파일 경로를 원본 파일명으로 변경하여 결괏값을 맞춤
            res["file"] = f.filename 
            results.append(res)
            
            # 업로드 실패 시 서버 로그 출력
            if not res["success"]:
                print(f"⚠️ 업로드 실패 [{f.filename}]: {res.get('error', '알 수 없는 오류')}")            
            if res["success"]:
                # DB 메타데이터 추출 및 등록 (임시 파일 경로에서 통계 정보 추출)
                meta = _extract_metadata_and_group(str(temp_path))
                
                # 파일명 기반으로 다시 그룹명 추출 (임시 경로 이름이 아닌 원본 파일명 기준)
                meta["version_group"] = Path(f.filename).stem
                group = re.sub(r'[-_.]?\d{4}[-_.]?\d{2}[-_.]?\d{2}[-_.]?', '', meta["version_group"]).strip('_.- ')
                if group:
                    meta["version_group"] = group
                    
                v_group = version_group.strip() if version_group.strip() else meta["version_group"]
                v_date = meta["version_date"]
                doc_id = f"doc_{uuid.uuid4().hex[:8]}"

                # AI 카테고리 자동 유추 (실패해도 업로드는 계속 진행)
                try:
                    category = _predict_category(f.filename)
                except Exception:
                    category = None

                conn.execute(
                    "UPDATE documents SET is_latest = 0 WHERE version_group = ? AND store_type = ?",
                    (v_group, store_type),
                )

                conn.execute(
                    """INSERT INTO documents
                    (id, file_name, display_name, version_group, version_date,
                     is_latest, store_name, store_type, 
                     doc_created_at, doc_modified_at, file_size, category,
                     uploaded_by)
                    VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?)""",
                    (doc_id, f.filename, f.filename, v_group, v_date,
                     store_name, store_type, 
                     meta["doc_created_at"].isoformat() if meta["doc_created_at"] else None,
                     meta["doc_modified_at"].isoformat() if meta["doc_modified_at"] else None,
                     meta["file_size"],
                     category,
                     admin["user_id"]),
                )
        conn.commit()
            
    success_count = sum(1 for r in results if r["success"])
    fail_count = len(results) - success_count
    
    # 실패한 파일 목록 구성
    fail_details = [f"{r['file']}: {r.get('error', '?')}" for r in results if not r["success"]]
    msg = f"{success_count}/{len(results)}개 파일 전송 완료"
    if fail_details:
        msg += f" (실패 {fail_count}건: {'; '.join(fail_details[:3])})"
    
    return {
        "message": msg,
        "results": results,
    }

# ── 문서 관리 API (admin only) ─────────────────────────

@router.get("/admin/documents")
def admin_list_documents(search: str = "", admin: dict = Depends(require_admin)):
    """업로드된 문서 목록 조회 (검색 + 버전 그룹별 정렬)"""
    conn = get_db()
    try:
        if search:
            rows = conn.execute(
                """SELECT d.*, u.username as uploaded_username
                FROM documents d LEFT JOIN users u ON d.uploaded_by = u.id
                WHERE d.file_name LIKE ? OR d.version_group LIKE ?
                ORDER BY d.version_group, d.version_date DESC""",
                (f"%{search}%", f"%{search}%"),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT d.*, u.username as uploaded_username
                FROM documents d LEFT JOIN users u ON d.uploaded_by = u.id
                ORDER BY d.version_group, d.version_date DESC""",
            ).fetchall()

        # 버전 그룹별로 정리
        groups = {}
        for r in rows:
            rd = dict(r)
            grp = rd["version_group"]
            if grp not in groups:
                groups[grp] = {"version_group": grp, "documents": [], "latest": None}
            groups[grp]["documents"].append(rd)
            if rd["is_latest"]:
                groups[grp]["latest"] = rd

        return {
            "groups": list(groups.values()),
            "total_documents": len(rows),
            "total_groups": len(groups),
        }
    finally:
        conn.close()


@router.get("/admin/documents/group/{version_group}")
def admin_get_document_group(version_group: str, admin: dict = Depends(require_admin)):
    """특정 버전 그룹의 모든 문서 버전 조회"""
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT d.*, u.username as uploaded_username
            FROM documents d LEFT JOIN users u ON d.uploaded_by = u.id
            WHERE d.version_group = ?
            ORDER BY d.version_date DESC""",
            (version_group,),
        ).fetchall()
        return {"version_group": version_group, "documents": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.put("/admin/documents/{doc_id}/set-latest")
def admin_set_latest(doc_id: str, admin: dict = Depends(require_admin)):
    """특정 문서를 해당 그룹의 최신 버전으로 수동 지정"""
    conn = get_db()
    try:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not doc:
            raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다")

        # 같은 그룹의 모든 문서 is_latest=0
        conn.execute(
            "UPDATE documents SET is_latest = 0 WHERE version_group = ?",
            (doc["version_group"],),
        )
        # 선택한 문서를 최신으로
        conn.execute("UPDATE documents SET is_latest = 1 WHERE id = ?", (doc_id,))
        conn.commit()
        return {"message": f"'{doc['file_name']}'이(가) 최신 버전으로 지정되었습니다"}
    finally:
        conn.close()
