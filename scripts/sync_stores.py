"""
Gemini File Search Store ↔ 로컬 DB 동기화 스크립트

기능:
  1. Gemini Store에 있는 파일 목록을 조회
  2. DB에 없는 파일 → DB에 INSERT (display_name 기준)
  3. DB에 있지만 Store에 없는 파일 → DB에서 DELETE (고아 레코드 정리)
  4. 동기화 결과 리포트 출력

사용법:
  .venv/bin/python scripts/sync_stores.py          # 동기화 실행
  .venv/bin/python scripts/sync_stores.py --reset   # Store 파일 전부 삭제 + DB 초기화
  .venv/bin/python scripts/sync_stores.py --list     # Store 파일 목록만 출력 (변경 없음)
"""
import sys
import os
import uuid
import argparse

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from google import genai
import sqlite3
from pathlib import Path


def get_client():
    return genai.Client(api_key=config.GEMINI_API_KEY)


def get_db():
    conn = sqlite3.connect(str(config.DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def list_store_files(client):
    """모든 Store의 파일 목록을 {display_name: file_info} 형태로 반환"""
    all_files = {}  # display_name -> {"store_name": ..., "file_name": ..., "store_display_name": ...}
    
    stores = list(client.file_search_stores.list())
    for store in stores:
        store_type = "primary" if "원본" in (store.display_name or "") else "correction"
        try:
            files = list(client.file_search_stores.list_files(store.name))
            for f in files:
                all_files[f.display_name] = {
                    "store_name": store.name,
                    "store_display_name": store.display_name,
                    "store_type": store_type,
                    "file_resource_name": f.name,
                    "display_name": f.display_name,
                }
        except Exception as e:
            print(f"  ⚠️ Store [{store.display_name}] 파일 목록 조회 실패: {e}")
    
    return stores, all_files


def cmd_list(client):
    """Store 파일 목록만 출력"""
    print("=" * 60)
    print("📋 Gemini File Search Store 파일 목록")
    print("=" * 60)
    
    stores, all_files = list_store_files(client)
    
    for store in stores:
        store_files = [f for f in all_files.values() if f["store_name"] == store.name]
        print(f"\n📦 {store.display_name} ({store.name})")
        print(f"   파일 수: {len(store_files)}개")
        for sf in sorted(store_files, key=lambda x: x["display_name"]):
            print(f"   └─ {sf['display_name']}")
    
    if not stores:
        print("📭 Store가 없습니다.")
    
    print(f"\n총 파일 수: {len(all_files)}개")


def cmd_sync(client):
    """Store 파일 목록과 DB를 동기화"""
    print("=" * 60)
    print("🔄 Gemini File Search Store ↔ DB 동기화")
    print("=" * 60)
    
    stores, store_files = list_store_files(client)
    print(f"\n📡 Store에서 {len(store_files)}개 파일 발견")
    
    conn = get_db()
    
    # DB의 현재 파일 목록
    db_rows = conn.execute("SELECT file_name, store_type FROM documents").fetchall()
    db_file_set = {(row["file_name"], row["store_type"]) for row in db_rows}
    store_file_set = {(f["display_name"], f["store_type"]) for f in store_files.values()}
    
    # Store에 있지만 DB에 없는 파일 → INSERT
    missing_in_db = store_file_set - db_file_set
    added = 0
    for display_name, store_type in sorted(missing_in_db):
        info = store_files[display_name]
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        stem = Path(display_name).stem
        
        conn.execute(
            """INSERT INTO documents
            (id, file_name, display_name, version_group, version_date,
             is_latest, store_name, store_type, uploaded_by)
            VALUES (?, ?, ?, ?, '', 1, ?, ?, 'admin_001')""",
            (doc_id, display_name, display_name, stem,
             info["store_name"], store_type),
        )
        added += 1
        print(f"  ➕ DB 추가: {display_name}")
    
    # DB에 있지만 Store에 없는 파일 → DELETE
    orphans_in_db = db_file_set - store_file_set
    removed = 0
    for file_name, store_type in sorted(orphans_in_db):
        conn.execute(
            "DELETE FROM documents WHERE file_name = ? AND store_type = ?",
            (file_name, store_type),
        )
        removed += 1
        print(f"  🗑️ DB 삭제 (고아 레코드): {file_name}")
    
    conn.commit()
    conn.close()
    
    # 리포트
    print(f"\n{'─' * 40}")
    print(f"📊 동기화 결과:")
    print(f"   Store 파일: {len(store_file_set)}개")
    print(f"   DB 추가:    +{added}개")
    print(f"   DB 삭제:    -{removed}개")
    print(f"   DB 최종:    {len(store_file_set)}개")
    print("✅ 동기화 완료!")


def cmd_reset(client):
    """Store 파일 전부 삭제 + DB 초기화"""
    print("=" * 60)
    print("🗑️ Gemini File Search Store + DB 전체 초기화")
    print("=" * 60)
    
    stores = list(client.file_search_stores.list())
    
    for store in stores:
        print(f"\n📦 Store: {store.display_name}")
        try:
            files = list(client.file_search_stores.list_files(store.name))
            if not files:
                print("   └─ (파일 없음)")
                continue
            
            print(f"   └─ {len(files)}개 파일 삭제 중...")
            deleted = 0
            for f in files:
                try:
                    client.file_search_stores.remove_file_from_store(
                        store_name=store.name,
                        file_name=f.name,
                    )
                    deleted += 1
                    if deleted % 10 == 0:
                        print(f"      ... {deleted}/{len(files)}")
                except Exception as e:
                    print(f"   ⚠️ 파일 삭제 실패 [{f.display_name}]: {e}")
            print(f"   ✅ {deleted}/{len(files)}개 파일 삭제 완료")
        except Exception as e:
            print(f"   ⚠️ 파일 목록 조회 실패: {e}")
    
    # DB 초기화
    conn = get_db()
    count = conn.execute("SELECT count(*) FROM documents").fetchone()[0]
    conn.execute("DELETE FROM documents")
    conn.commit()
    conn.close()
    print(f"\n🗄️ DB documents 테이블: {count}개 레코드 삭제")
    print("\n🎉 전체 초기화 완료! 서버를 재시작하고 새로 업로드하세요.")


def main():
    parser = argparse.ArgumentParser(description="Gemini File Search Store ↔ DB 동기화")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--list", action="store_true", help="Store 파일 목록만 출력")
    group.add_argument("--reset", action="store_true", help="Store + DB 전체 초기화")
    group.add_argument("--sync", action="store_true", default=True, help="Store ↔ DB 동기화 (기본)")
    
    args = parser.parse_args()
    client = get_client()
    
    if args.list:
        cmd_list(client)
    elif args.reset:
        cmd_reset(client)
    else:
        cmd_sync(client)


if __name__ == "__main__":
    main()
