"""지혜의 샘 — 하이브리드 RAG 건강교육 챗봇 엔드포인트.

원래 app/apis/v1/wellness_routers.py 안에 있던 `/health-education/questions`만 이 파일로
따로 뺐다. 웨어러블/건강검진 OCR 쪽(app/apis/v1/wellness_routers.py, PR #47)과 이 RAG
챗봇 쪽이 같은 파일을 건드리면서 생기던 merge 충돌 가능성을 줄이기 위한 분리다.

퀴즈(/health-education/quizzes, .../answers)는 RAG로 생성된 문항을 다루긴 하지만
엔드포인트 자체는 그대로 wellness_routers.py에 남아 있다(이번 분리 요청 범위 밖).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.apis.responses import envelope
from app.dependencies.security import get_request_user
from app.dtos.wellness import RagQuestionRequest, RagQuestionResponse
from app.models.users import User
from src.rag.engine import answer_with_sources

rag_router = APIRouter(tags=["Health education RAG"])


@rag_router.post("/health-education/questions", response_model=RagQuestionResponse)
async def ask_health_education(request: RagQuestionRequest, user: Annotated[User, Depends(get_request_user)]):
    _ = user
    result = await answer_with_sources(request.question)
    result["medical_notice"] = "일반 건강교육 정보이며 개인 진단·처방을 대신하지 않습니다."
    return envelope(result)
