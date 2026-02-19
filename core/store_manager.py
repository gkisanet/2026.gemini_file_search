"""
File Search Store 관리 모듈
원본 사규 Store와 교정 데이터 Store의 CRUD 및 상태 관리
"""
import time
from google import genai
from google.genai import types
import config


def _get_client() -> genai.Client:
    """Gemini API 클라이언트 생성"""
    return genai.Client(api_key=config.GEMINI_API_KEY)


def get_or_create_store(display_name: str) -> str:
    """
    display_name으로 기존 Store를 찾거나 없으면 새로 생성.
    Store의 name(리소스 ID)을 반환한다.
    """
    client = _get_client()

    # 기존 Store 검색
    for store in client.file_search_stores.list():
        if store.display_name == display_name:
            return store.name

    # 새 Store 생성
    store = client.file_search_stores.create(config={"display_name": display_name})
    return store.name


def list_stores() -> list[dict]:
    """모든 File Search Store 목록 반환"""
    client = _get_client()
    stores = []
    for store in client.file_search_stores.list():
        stores.append({
            "name": store.name,
            "display_name": store.display_name,
        })
    return stores


def get_store_documents(store_name: str) -> list[dict]:
    """특정 Store의 문서 목록 반환"""
    client = _get_client()
    docs = []
    for doc in client.file_search_stores.documents.list(parent=store_name):
        docs.append({
            "name": doc.name,
            "display_name": getattr(doc, "display_name", ""),
        })
    return docs


def delete_document(document_name: str):
    """Store에서 특정 문서 삭제"""
    client = _get_client()
    client.file_search_stores.documents.delete(name=document_name)


def delete_store(store_name: str, force: bool = True):
    """Store 삭제 (force=True면 문서 포함)"""
    client = _get_client()
    client.file_search_stores.delete(name=store_name, config={"force": force})
