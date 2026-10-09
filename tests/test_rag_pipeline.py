"""지혜의 샘 하이브리드 RAG 파이프라인(청킹·임베딩·검색·생성·검증) 단위 테스트.

기존 tests/test_wellness_extensions.py의 answer_with_sources 계약(응급/복약 안전검사,
grounded/insufficient_evidence 상태, citations 형식) 테스트는 그대로 유지하고, 여기서는
새로 추가된 각 단계(②~⑥)를 독립적으로 검증한다.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.core import config
from src.rag import engine
from src.rag.chunking import Chunk, split_into_chunks, split_sentences
from src.rag.embeddings import (
    DevelopmentEmbeddingProvider,
    EmbeddingError,
    OpenAIEmbeddingProvider,
    cosine_similarity,
    get_embedding_provider,
)
from src.rag.generation import (
    AnswerGenerationError,
    DevelopmentAnswerGenerationProvider,
    GeneratedAnswer,
    GeneratedSentence,
    OpenAIAnswerGenerationProvider,
    get_generation_provider,
)
from src.rag.retrieval import hybrid_search, top_chunks
from src.rag.verification import cited_document_ids, verify_sentences

# ---------------------------------------------------------------------------
# ① 문서 청킹
# ---------------------------------------------------------------------------


def test_split_sentences_breaks_on_terminator_followed_by_space():
    text = "혈당 목표는 6.5% 미만입니다. 혈압은 130/80mmHg 미만으로 유지합니다."
    sentences = split_sentences(text)
    assert sentences == (
        "혈당 목표는 6.5% 미만입니다.",
        "혈압은 130/80mmHg 미만으로 유지합니다.",
    )


def test_split_sentences_does_not_break_on_decimal_point_without_space():
    text = "당화혈색소 6.5%미만을 목표로 합니다."
    sentences = split_sentences(text)
    assert len(sentences) == 1
    assert "6.5%" in sentences[0]


def test_split_sentences_merges_short_trailing_fragment_into_previous():
    text = "가. 나다라. 마."
    sentences = split_sentences(text)
    # "나다라."(4자)와 "마."(2자) 모두 _MIN_CHUNK_LENGTH(8자) 미만이라 차례로 앞 문장에 합쳐져,
    # 결과적으로 문장 전체가 첫 조각 하나로 합쳐진다.
    assert sentences == ("가. 나다라. 마.",)


def test_split_into_chunks_ids_are_stable_and_ordered():
    chunks = split_into_chunks("doc-a", "첫 문장입니다. 두 번째 문장입니다. 세 번째 문장입니다.")
    assert [c.chunk_id for c in chunks] == ["doc-a#0", "doc-a#1", "doc-a#2"]
    assert [c.index for c in chunks] == [0, 1, 2]
    assert all(c.document_id == "doc-a" for c in chunks)


def test_split_into_chunks_falls_back_to_whole_text_when_no_sentence_boundary():
    chunks = split_into_chunks("doc-b", "문장부호 없이 쭉 이어지는 텍스트")
    assert len(chunks) == 1
    assert chunks[0].chunk_id == "doc-b#0"


def test_engine_builds_one_chunk_index_per_approved_document():
    document_ids_with_chunks = {chunk.document_id for chunk in engine.ALL_CHUNKS}
    assert document_ids_with_chunks == {document.document_id for document in engine.APPROVED_DOCUMENTS}
    assert len(engine.ALL_CHUNKS) >= len(engine.APPROVED_DOCUMENTS)


# ---------------------------------------------------------------------------
# ② 임베딩 provider
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_development_embedding_provider_is_deterministic():
    provider = DevelopmentEmbeddingProvider()
    first = await provider.embed(["당뇨병 예방을 위한 생활습관"])
    second = await provider.embed(["당뇨병 예방을 위한 생활습관"])
    assert first == second


@pytest.mark.asyncio
async def test_development_embedding_provider_self_similarity_is_near_one():
    provider = DevelopmentEmbeddingProvider()
    [vector] = await provider.embed(["동일한 문장 유사도 테스트"])
    assert cosine_similarity(vector, vector) == pytest.approx(1.0, abs=1e-9)


@pytest.mark.asyncio
async def test_development_embedding_provider_returns_zero_vector_for_empty_text():
    provider = DevelopmentEmbeddingProvider()
    [vector] = await provider.embed([""])
    assert cosine_similarity(vector, vector) == 0.0


def test_cosine_similarity_handles_empty_vectors():
    assert cosine_similarity([], [1.0]) == 0.0
    assert cosine_similarity([0.0, 0.0], [0.0, 0.0]) == 0.0


def test_get_embedding_provider_rejects_unknown_provider_name(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "HEALTH_EDUCATION_EMBEDDING_PROVIDER", "not-a-real-provider")
    with pytest.raises(EmbeddingError):
        get_embedding_provider()


def test_openai_embedding_provider_requires_api_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    with pytest.raises(EmbeddingError):
        OpenAIEmbeddingProvider()


@pytest.mark.asyncio
async def test_engine_fails_closed_when_embedding_provider_is_unavailable(monkeypatch: pytest.MonkeyPatch):
    async def unavailable_search(*args: object, **kwargs: object):
        del args, kwargs
        raise EmbeddingError("provider unavailable")

    monkeypatch.setattr(engine, "hybrid_search", unavailable_search)
    result = await engine.answer_with_sources("당뇨병 운동 방법을 알려주세요")

    assert result["answer_status"] == "insufficient_evidence"
    assert result["citations"] == []
    assert "잠시 후" in result["answer"]


class _FakeEmbeddingsAsyncClient:
    def __init__(self, *args: object, **kwargs: object) -> None:
        del args, kwargs

    async def __aenter__(self) -> _FakeEmbeddingsAsyncClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        del exc_info

    async def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]):
        del url, headers
        texts = json["input"]
        # 일부러 역순으로 반환해서, provider가 index로 재정렬하는지 검증한다.
        data = [
            {"index": index, "embedding": [float(len(text)), 0.0]} for index, text in reversed(list(enumerate(texts)))
        ]
        return _FakeHttpResponse({"data": data})


class _FakeHttpResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


@pytest.mark.asyncio
async def test_openai_embedding_provider_reorders_by_index(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(httpx, "AsyncClient", _FakeEmbeddingsAsyncClient)
    provider = OpenAIEmbeddingProvider()
    vectors = await provider.embed(["ab", "abcd"])
    assert vectors == [[2.0, 0.0], [4.0, 0.0]]


# ---------------------------------------------------------------------------
# ②④ 하이브리드 검색·재정렬
# ---------------------------------------------------------------------------


def _chunk(document_id: str, index: int, text: str) -> Chunk:
    return Chunk(chunk_id=f"{document_id}#{index}", document_id=document_id, index=index, text=text)


@pytest.mark.asyncio
async def test_hybrid_search_ranks_keyword_match_above_unrelated_chunk():
    chunks = (
        _chunk("relevant-doc", 0, "당뇨병 환자는 규칙적으로 운동하는 것이 좋습니다."),
        _chunk("unrelated-doc", 0, "오늘 날씨는 맑고 기온은 20도입니다."),
    )
    keyword_lookup = {"relevant-doc": ("당뇨", "운동"), "unrelated-doc": ("날씨",)}
    scored = await hybrid_search(
        "당뇨병 환자 운동은 어떻게 하나요?",
        chunks=chunks,
        keyword_lookup=keyword_lookup,
        embedding_provider=DevelopmentEmbeddingProvider(),
    )
    assert scored[0].chunk.document_id == "relevant-doc"
    assert scored[0].combined_score > scored[1].combined_score


@pytest.mark.asyncio
async def test_hybrid_search_gives_near_zero_combined_score_for_fully_unrelated_question():
    chunks = (
        _chunk("diabetes-doc", 0, "당뇨병 환자는 규칙적으로 운동하는 것이 좋습니다."),
        _chunk("diet-doc", 0, "식이요법에서는 탄수화물 섭취량 조절이 중요합니다."),
    )
    keyword_lookup = {"diabetes-doc": ("당뇨", "운동"), "diet-doc": ("식이요법", "탄수화물")}
    scored = await hybrid_search(
        "주식 투자는 어떻게 시작하나요",
        chunks=chunks,
        keyword_lookup=keyword_lookup,
        embedding_provider=DevelopmentEmbeddingProvider(),
    )
    # 이 배치 안에서 정규화하지 않으므로, 진짜 무관한 질문은 결합 점수가 낮은 절대값에 머물러야 한다
    # (배치 내 min-max 정규화를 쓰면 이 값이 항상 1.0 근처로 튀는 회귀 버그가 있었다).
    assert scored[0].combined_score < config.HEALTH_EDUCATION_RELEVANCE_THRESHOLD


def test_top_chunks_respects_limit():
    scored_chunks = [
        type("S", (), {"chunk": _chunk("d", i, f"t{i}"), "combined_score": 1.0 - i * 0.1})() for i in range(10)
    ]
    limited = top_chunks(tuple(scored_chunks), limit=3)
    assert len(limited) == 3
    assert [c.index for c in limited] == [0, 1, 2]


# ---------------------------------------------------------------------------
# ⑤ LLM 제한 생성
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_development_generation_provider_cites_each_chunk_to_itself():
    chunks = (_chunk("doc-a", 0, "문장 A"), _chunk("doc-a", 1, "문장 B"))
    generated = await DevelopmentAnswerGenerationProvider().generate("질문", chunks)
    assert generated.provider_kind == "development_concat"
    assert [s.text for s in generated.sentences] == ["문장 A", "문장 B"]
    assert generated.sentences[0].supporting_chunk_ids == ("doc-a#0",)


def test_get_generation_provider_rejects_unknown_provider_name(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "HEALTH_EDUCATION_GENERATION_PROVIDER", "not-a-real-provider")
    with pytest.raises(AnswerGenerationError):
        get_generation_provider()


def test_openai_generation_provider_requires_api_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    with pytest.raises(AnswerGenerationError):
        OpenAIAnswerGenerationProvider()


def test_openai_generation_provider_parses_valid_sentences():
    provider = object.__new__(OpenAIAnswerGenerationProvider)
    valid_ids = {"doc-a#0", "doc-a#1"}
    content = json.dumps(
        {
            "sentences": [
                {"text": "첫 문장", "supporting_chunk_ids": ["doc-a#0"]},
                {"text": "  ", "supporting_chunk_ids": ["doc-a#1"]},  # 빈 문장은 제외
                {"text": "출처 없는 문장", "supporting_chunk_ids": ["doc-x#99"]},  # 유효하지 않은 id는 제거
            ]
        }
    )
    sentences = provider._parse_sentences(content, valid_ids)
    assert [s.text for s in sentences] == ["첫 문장", "출처 없는 문장"]
    assert sentences[0].supporting_chunk_ids == ("doc-a#0",)
    assert sentences[1].supporting_chunk_ids == ()


@pytest.mark.parametrize(
    "content",
    ["not json", "[]", "null", '{"sentences": "no"}', '{"sentences": [1]}'],
)
def test_openai_generation_provider_rejects_malformed_content(content: str):
    provider = object.__new__(OpenAIAnswerGenerationProvider)
    with pytest.raises(AnswerGenerationError):
        provider._parse_sentences(content, set())


def test_openai_generation_provider_silently_skips_sentence_with_non_string_text():
    # 스키마 전체를 실패시키기보다, 개별 문장 하나가 이상해도 나머지는 살리는 쪽을 선택했다.
    provider = object.__new__(OpenAIAnswerGenerationProvider)
    content = json.dumps({"sentences": [{"text": 1}, {"text": "정상 문장", "supporting_chunk_ids": []}]})
    sentences = provider._parse_sentences(content, set())
    assert [s.text for s in sentences] == ["정상 문장"]


class _FakeChatAsyncClient:
    def __init__(self, *args: object, **kwargs: object) -> None:
        del args, kwargs

    async def __aenter__(self) -> _FakeChatAsyncClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        del exc_info

    async def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]):
        del url, headers, json
        content = json_module_dumps(
            {"sentences": [{"text": "근거 기반 답변입니다.", "supporting_chunk_ids": ["doc-a#0"]}]}
        )
        return _FakeHttpResponse({"choices": [{"message": {"content": content}}]})


def json_module_dumps(payload: dict[str, object]) -> str:
    return json.dumps(payload)


@pytest.mark.asyncio
async def test_openai_generation_provider_end_to_end_with_fake_http(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(httpx, "AsyncClient", _FakeChatAsyncClient)
    provider = OpenAIAnswerGenerationProvider()
    chunks = (_chunk("doc-a", 0, "원본 근거 문장"),)
    generated = await provider.generate("질문", chunks)
    assert generated.sentences[0].text == "근거 기반 답변입니다."
    assert generated.sentences[0].supporting_chunk_ids == ("doc-a#0",)


# ---------------------------------------------------------------------------
# ⑥ 문장별 출처 검사
# ---------------------------------------------------------------------------


def test_verify_sentences_drops_sentence_with_no_supporting_chunk_id():
    chunks_by_id = {"doc-a#0": _chunk("doc-a", 0, "당뇨병 환자는 규칙적으로 운동해야 합니다.")}
    generated = GeneratedAnswer(
        provider_kind="test",
        sentences=(GeneratedSentence(text="근거 없는 문장", supporting_chunk_ids=()),),
    )
    assert verify_sentences(generated, chunks_by_id) == ()


def test_verify_sentences_drops_sentence_that_does_not_lexically_match_its_cited_chunk():
    chunks_by_id = {"doc-a#0": _chunk("doc-a", 0, "당뇨병 환자는 규칙적으로 운동해야 합니다.")}
    generated = GeneratedAnswer(
        provider_kind="test",
        sentences=(
            GeneratedSentence(text="전혀 다른 내용의 문장입니다 완전히 무관함", supporting_chunk_ids=("doc-a#0",)),
        ),
    )
    assert verify_sentences(generated, chunks_by_id) == ()


def test_verify_sentences_keeps_sentence_with_real_lexical_overlap():
    chunks_by_id = {"doc-a#0": _chunk("doc-a", 0, "당뇨병 환자는 규칙적으로 운동해야 합니다.")}
    generated = GeneratedAnswer(
        provider_kind="test",
        sentences=(
            GeneratedSentence(text="당뇨병 환자는 규칙적으로 운동해야 합니다.", supporting_chunk_ids=("doc-a#0",)),
        ),
    )
    assert verify_sentences(generated, chunks_by_id) == ("당뇨병 환자는 규칙적으로 운동해야 합니다.",)


def test_cited_document_ids_dedups_and_preserves_first_appearance_order():
    chunks_by_id = {
        "doc-a#0": _chunk("doc-a", 0, "a"),
        "doc-b#0": _chunk("doc-b", 0, "b"),
        "doc-a#1": _chunk("doc-a", 1, "a2"),
    }
    generated = GeneratedAnswer(
        provider_kind="test",
        sentences=(
            GeneratedSentence(text="s1", supporting_chunk_ids=("doc-b#0",)),
            GeneratedSentence(text="s2", supporting_chunk_ids=("doc-a#0", "doc-a#1")),
        ),
    )
    verified = ("s1", "s2")
    assert cited_document_ids(generated, chunks_by_id, verified) == ("doc-b", "doc-a")


def test_cited_document_ids_ignores_sentences_that_were_not_verified():
    chunks_by_id = {"doc-a#0": _chunk("doc-a", 0, "a")}
    generated = GeneratedAnswer(
        provider_kind="test",
        sentences=(GeneratedSentence(text="탈락된 문장", supporting_chunk_ids=("doc-a#0",)),),
    )
    assert cited_document_ids(generated, chunks_by_id, verified_sentences=()) == ()


# ---------------------------------------------------------------------------
# 전체 파이프라인(answer_with_sources) 회귀 테스트
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_answer_with_sources_reports_hybrid_retrieval_method_when_grounded():
    result = await engine.answer_with_sources("당뇨 예방을 위해 어떤 생활습관을 기록하면 좋나요?")
    assert result["answer_status"] == "grounded"
    assert result["retrieval_method"] == "hybrid_keyword_embedding_v2"
    assert len(result["citations"]) <= config.HEALTH_EDUCATION_MAX_CITATIONS


@pytest.mark.asyncio
async def test_answer_with_sources_returns_insufficient_evidence_for_unrelated_question():
    # development 임베딩(해싱 트릭)은 실제 의미 이해가 아니라 문자 n그램 근사치이므로, 완전히
    # 무관한 질문이 어쩌다 관련도 임계값을 넘지 않는지가 핵심 회귀 지점이다.
    result = await engine.answer_with_sources("주식 투자는 어떻게 시작하나요")
    assert result["answer_status"] == "insufficient_evidence"
    assert result["citations"] == []
    assert result["retrieval_method"] == "hybrid_keyword_embedding_v2"


@pytest.mark.asyncio
async def test_answer_with_sources_falls_back_gracefully_when_generation_fails(monkeypatch: pytest.MonkeyPatch):
    class _BrokenGenerationProvider:
        provider_kind = "broken"

        async def generate(self, question, chunks):
            del question, chunks
            raise AnswerGenerationError("boom")

    monkeypatch.setattr(engine, "get_generation_provider", lambda: _BrokenGenerationProvider())
    result = await engine.answer_with_sources("당뇨 예방을 위해 어떤 생활습관을 기록하면 좋나요?")
    # 프론트가 grounded/insufficient_evidence/medical_safety_refusal 세 가지만 허용 목록으로 처리하므로
    # (그 외 값은 화면에서 에러로 fail-closed 처리됨), 생성 실패도 insufficient_evidence로 폴백해야 한다.
    assert result["answer_status"] == "insufficient_evidence"
    assert result["citations"] == []


@pytest.mark.asyncio
async def test_answer_with_sources_still_short_circuits_safety_checks_before_retrieval(
    monkeypatch: pytest.MonkeyPatch,
):
    # 안전검사(응급/복약)는 하이브리드 검색보다 먼저 실행되어야 하므로, 검색 단계가 절대 호출되지
    # 않는지까지 확인한다(호출되면 예외를 던지도록 해서 검증).
    async def _must_not_be_called(*args: object, **kwargs: object):
        raise AssertionError("safety short-circuit 이후에는 hybrid_search가 호출되면 안 됩니다")

    monkeypatch.setattr(engine, "hybrid_search", _must_not_be_called)
    emergency = await engine.answer_with_sources("갑자기 가슴 통증이 심하고 숨쉬기 힘들어요")
    assert emergency["answer_status"] == "emergency_redirect"
    refusal = await engine.answer_with_sources("당뇨약 용량을 줄여도 되나요?")
    assert refusal["answer_status"] == "medical_safety_refusal"
