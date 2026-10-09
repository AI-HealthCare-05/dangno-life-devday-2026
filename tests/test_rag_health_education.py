"""지혜의 샘 하이브리드 RAG 엔진(answer_with_sources) 자체를 직접 호출하는 계약 테스트.

원래 tests/test_wellness_extensions.py 안에 있던 순수 RAG 테스트 4개만 이 파일로 뺐다.
(다른 엔드포인트와 함께 묶여 있는 test_wearable_rag_cv_ocr_notification_and_pdf_contracts는
웨어러블/식단/OCR/알림/PDF까지 같이 검증하는 통합 계약 테스트라 그대로 남겨뒀다.)
"""

from __future__ import annotations

import pytest

from app.dtos.wellness import RagQuestionResponse
from src.rag.engine import answer_with_sources


@pytest.mark.asyncio
async def test_rag_returns_citations_and_refuses_medication_changes() -> None:
    grounded = await answer_with_sources("당뇨 예방을 위해 어떤 생활습관을 기록하면 좋나요?")
    assert grounded["answer_status"] == "grounded"
    assert grounded["citations"]
    assert all(item["url"].startswith("https://") for item in grounded["citations"])
    assert all("checked_at" in item for item in grounded["citations"])

    refused = await answer_with_sources("당뇨약 용량을 줄여도 되나요?")
    assert refused["answer_status"] == "medical_safety_refusal"
    assert "의료진" in refused["answer"]


@pytest.mark.asyncio
async def test_rag_redirects_emergency_symptoms_before_normal_answer() -> None:
    emergency = await answer_with_sources("갑자기 가슴 통증이 심하고 숨쉬기 힘들어요")
    assert emergency["answer_status"] == "emergency_redirect"
    assert "119" in emergency["answer"]
    assert emergency["citations"]
    assert emergency["citations"][0]["document_id"] == "kdca-hyperglycemia-emergency"

    unconscious = await answer_with_sources("어지러워서 쓰러졌는데 의식이 흐려요")
    assert unconscious["answer_status"] == "emergency_redirect"


@pytest.mark.asyncio
async def test_rag_emergency_takes_priority_over_medication_pattern() -> None:
    result = await answer_with_sources("의식을 잃었는데 약을 늘려도 되나요?")
    assert result["answer_status"] == "emergency_redirect"


@pytest.mark.asyncio
async def test_rag_diet_and_complication_questions_are_grounded_in_new_documents() -> None:
    diet = await answer_with_sources("당뇨병 식이요법에서 탄수화물은 얼마나 먹어야 하나요?")
    assert diet["answer_status"] == "grounded"
    assert any(item["document_id"] == "kdca-diabetes-diet" for item in diet["citations"])

    complications = await answer_with_sources("당뇨병 합병증으로 어떤 검진을 받아야 하나요?")
    assert complications["answer_status"] == "grounded"
    assert any(item["document_id"] == "kdca-diabetes-complications" for item in complications["citations"])


def test_rag_response_model_documents_the_complete_envelope() -> None:
    schema = RagQuestionResponse.model_json_schema()
    data_schema = schema["$defs"]["RagQuestionDataResponse"]

    assert set(data_schema["required"]) == {
        "answer",
        "answer_status",
        "citations",
        "retrieval_method",
        "medical_notice",
    }
    assert set(schema["required"]) == {"data", "meta"}
