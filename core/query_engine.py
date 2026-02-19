"""
RAG 질의 엔진
이중 File Search Store(원본 + 교정)를 활용한 Gemini 질의 처리
대화 컨텍스트 유지, Citation 파싱
"""
import json
from google import genai
from google.genai import types
import config
from core.store_manager import get_or_create_store


def _get_client() -> genai.Client:
    return genai.Client(api_key=config.GEMINI_API_KEY)


def _build_conversation_contents(history: list[dict], new_message: str) -> list:
    """대화 히스토리 + 신규 메시지를 Gemini contents 형식으로 변환"""
    contents = []

    for msg in history:
        contents.append(types.Content(
            role=msg["role"],
            parts=[types.Part(text=msg["content"])],
        ))

    # 신규 사용자 메시지
    contents.append(types.Content(
        role="user",
        parts=[types.Part(text=new_message)],
    ))
    return contents


def _parse_citations(response) -> list[dict]:
    """응답에서 Citation(출처 정보) 추출"""
    citations = []
    try:
        metadata = response.candidates[0].grounding_metadata
        if metadata and hasattr(metadata, "grounding_chunks"):
            for chunk in metadata.grounding_chunks:
                citation = {}
                if hasattr(chunk, "retrieved_context"):
                    ctx = chunk.retrieved_context
                    citation["title"] = getattr(ctx, "title", "")
                    citation["uri"] = getattr(ctx, "uri", "")
                if hasattr(chunk, "text"):
                    citation["text"] = chunk.text
                if citation:
                    citations.append(citation)
    except (AttributeError, IndexError):
        pass
    return citations


def query(
    message: str,
    history: list[dict] | None = None,
    use_correction_store: bool = True,
) -> dict:
    """
    RAG 질의 수행.

    Args:
        message: 사용자 질문
        history: 이전 대화 메시지 목록 [{"role": "user"|"assistant", "content": "..."}]
        use_correction_store: 교정 Store도 검색에 포함할지 여부

    Returns:
        {
            "answer": str,
            "citations": list[dict],
            "model": str,
        }
    """
    client = _get_client()
    history = history or []

    # Store 이름 조회 (없으면 생성)
    primary_store = get_or_create_store(config.PRIMARY_STORE_DISPLAY_NAME)
    store_names = [primary_store]

    if use_correction_store:
        correction_store = get_or_create_store(config.CORRECTION_STORE_DISPLAY_NAME)
        store_names.append(correction_store)

    # 대화 컨텍스트 구성
    contents = _build_conversation_contents(history, message)

    # Gemini 호출 (File Search 도구 포함)
    response = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=config.SYSTEM_PROMPT,
            tools=[
                types.Tool(
                    file_search=types.FileSearch(
                        file_search_store_names=store_names
                    )
                )
            ],
        ),
    )

    # 응답 파싱
    answer = response.text if response.text else "답변을 생성할 수 없습니다."
    citations = _parse_citations(response)

    return {
        "answer": answer,
        "citations": citations,
        "model": config.GEMINI_MODEL,
    }


def generate_session_title(first_message: str) -> str:
    """첫 메시지를 기반으로 세션 제목을 자동 생성"""
    client = _get_client()
    try:
        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=f'다음 질문을 10자 이내의 한국어 제목으로 요약해줘. 제목만 출력하고 다른 설명은 하지 마:\n"{first_message}"',
        )
        title = response.text.strip().strip('"').strip("'")
        # 너무 길면 자르기
        return title[:30] if len(title) > 30 else title
    except Exception:
        return first_message[:20] + "..." if len(first_message) > 20 else first_message
