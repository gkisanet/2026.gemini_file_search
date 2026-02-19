"""
피드백 분석기
사용자의 오류 지적 메시지를 Gemini로 분석하여 구조화된 교정 데이터를 추출
"""
import json
from google import genai
from google.genai import types
import config

# 피드백 분석용 프롬프트
ANALYSIS_PROMPT = """사용자가 AI의 답변이 틀렸다고 지적하는 대화를 분석해주세요.

[분석 대상 대화]
- AI의 질문에 대한 원래 답변: {ai_answer}
- 사용자의 피드백: {user_feedback}
- 원래 질문: {original_question}

[요청 사항]
아래 JSON 형식으로만 응답하세요. 다른 텍스트는 포함하지 마세요:
{{
    "original_question": "사용자가 원래 물었던 질문을 정리",
    "ai_wrong_answer": "AI가 틀리게 답한 내용 요약",
    "user_correction": "사용자가 제시한 올바른 정보",
    "extracted_fact": "교정된 정확한 사실을 하나의 명확한 문장으로 정리",
    "confidence": 0.0~1.0 사이의 신뢰도 (사용자 피드백이 명확할수록 높음)
}}
"""


def _get_client() -> genai.Client:
    return genai.Client(api_key=config.GEMINI_API_KEY)


def analyze_feedback(
    original_question: str,
    ai_answer: str,
    user_feedback: str,
) -> dict | None:
    """
    사용자 피드백을 Gemini로 분석하여 구조화된 교정 데이터를 추출.

    Returns:
        분석 결과 dict 또는 실패 시 None
        {
            "original_question": str,
            "ai_wrong_answer": str,
            "user_correction": str,
            "extracted_fact": str,
            "confidence": float,
        }
    """
    client = _get_client()

    prompt = ANALYSIS_PROMPT.format(
        ai_answer=ai_answer,
        user_feedback=user_feedback,
        original_question=original_question,
    )

    try:
        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
        )

        text = response.text.strip()
        # JSON 블록 추출 (마크다운 코드블록 감싸진 경우 처리)
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        result = json.loads(text)
        return result

    except (json.JSONDecodeError, Exception) as e:
        # 분석 실패 시 원본 데이터로 폴백
        return {
            "original_question": original_question,
            "ai_wrong_answer": ai_answer[:200],
            "user_correction": user_feedback,
            "extracted_fact": user_feedback,
            "confidence": 0.5,
        }


def generate_correction_text(analysis: dict) -> str:
    """
    분석 결과를 File Search Store에 업로드할 교정 텍스트로 변환.
    자연어 Q&A 형식으로 생성하여 검색 시 매칭되기 쉽게 한다.
    """
    return (
        f"[교정 데이터]\n"
        f"질문: {analysis['original_question']}\n"
        f"정답: {analysis['extracted_fact']}\n"
        f"참고: 이전 답변 \"{analysis['ai_wrong_answer']}\"은(는) 부정확합니다.\n"
        f"교정 내용: {analysis['user_correction']}\n"
        f"신뢰도: {analysis.get('confidence', 'N/A')}\n"
    )
