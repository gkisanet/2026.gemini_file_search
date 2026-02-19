"""
SQLite 데이터베이스 초기화 및 연결 관리
앱 시작 시 테이블 생성 + 기본 admin/user 계정 시드
"""
import sqlite3
from pathlib import Path
from passlib.context import CryptContext
import config

# 비밀번호 해싱 컨텍스트
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 테이블 생성 SQL
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'user' CHECK(role IN ('user', 'admin')),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    title TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    citations TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS corrections (
    id TEXT PRIMARY KEY,
    session_id TEXT REFERENCES sessions(id),
    submitted_by TEXT NOT NULL REFERENCES users(id),
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected','superseded')),
    original_question TEXT,
    ai_wrong_answer TEXT,
    user_correction TEXT,
    extracted_fact TEXT,
    confidence REAL,
    correction_text TEXT,
    store_document_name TEXT,
    reviewed_by TEXT REFERENCES users(id),
    reviewed_at DATETIME,
    reject_reason TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    file_name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    version_group TEXT NOT NULL,
    version_date TEXT,
    is_latest INTEGER DEFAULT 1,
    store_name TEXT NOT NULL,
    store_type TEXT DEFAULT 'primary' CHECK(store_type IN ('primary', 'correction')),
    uploaded_by TEXT REFERENCES users(id),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

# 기본 시드 계정
SEED_USERS = [
    ("admin_001", "admin", "admin123", "admin"),
    ("user_001", "user", "user123", "user"),
]


def get_db() -> sqlite3.Connection:
    """SQLite 연결 반환. Row factory 설정하여 dict-like 접근 가능."""
    conn = sqlite3.connect(str(config.DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")      # 동시성 향상
    conn.execute("PRAGMA foreign_keys=ON")        # FK 제약 활성화
    return conn


def init_db():
    """테이블 생성 + 시드 데이터 삽입 (최초 1회)."""
    conn = get_db()
    try:
        conn.executescript(SCHEMA_SQL)

        # 시드 사용자 삽입 (이미 있으면 무시)
        for uid, username, password, role in SEED_USERS:
            try:
                conn.execute(
                    "INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, ?, ?)",
                    (uid, username, pwd_context.hash(password), role),
                )
            except sqlite3.IntegrityError:
                pass  # 이미 존재하는 계정은 건너뜀

        conn.commit()
    finally:
        conn.close()
