"""
JWT 인증 모듈
로그인 검증, 토큰 발급/검증, 역할 기반 접근 제어
"""
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import config
from server.database import get_db, verify_password

security = HTTPBearer()


def create_access_token(user_id: str, username: str, role: str) -> str:
    """JWT 액세스 토큰 생성"""
    expire = datetime.now(timezone.utc) + timedelta(minutes=config.JWT_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """JWT 토큰 디코딩 및 검증"""
    try:
        payload = jwt.decode(token, config.JWT_SECRET_KEY, algorithms=[config.JWT_ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 인증 토큰입니다",
        )


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """현재 인증된 사용자 정보 반환 (의존성 주입용)"""
    payload = decode_token(credentials.credentials)
    return {
        "user_id": payload["sub"],
        "username": payload["username"],
        "role": payload["role"],
    }


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """관리자 권한 검증 (의존성 주입용)"""
    if current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자 권한이 필요합니다",
        )
    return current_user


def authenticate_user(username: str, password: str) -> dict | None:
    """사용자 인증. 성공 시 사용자 정보 dict 반환, 실패 시 None."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, username, password_hash, role FROM users WHERE username = ?",
            (username,),
        ).fetchone()

        if row and verify_password(password, row["password_hash"]):
            return {"user_id": row["id"], "username": row["username"], "role": row["role"]}
        return None
    finally:
        conn.close()
