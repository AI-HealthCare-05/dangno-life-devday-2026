from __future__ import annotations

import uuid
from typing import Any

import httpx

from app.core import config
from src.rag.chunking import Chunk
from src.rag.embeddings import EmbeddingProvider
from src.rag.retrieval import ScoredChunk


class QdrantError(RuntimeError):
    """Raised when the external vector index cannot serve a valid response."""


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if config.QDRANT_API_KEY:
        headers["api-key"] = config.QDRANT_API_KEY
    return headers


def _collection_url() -> str:
    base = config.QDRANT_URL.rstrip("/")
    return f"{base}/collections/{config.QDRANT_COLLECTION}"


async def qdrant_search(
    question: str,
    *,
    embedding_provider: EmbeddingProvider,
) -> tuple[ScoredChunk, ...]:
    [query_vector] = await embedding_provider.embed([question.strip().casefold()])
    payload = {
        "query": query_vector,
        "limit": config.HEALTH_EDUCATION_TOP_K,
        "with_payload": True,
        "filter": {"must": [{"key": "approved", "match": {"value": True}}]},
    }
    try:
        async with httpx.AsyncClient(timeout=config.HEALTH_EDUCATION_TIMEOUT_SECONDS) as client:
            response = await client.post(f"{_collection_url()}/points/query", headers=_headers(), json=payload)
            response.raise_for_status()
            points = response.json()["result"]["points"]
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise QdrantError("Qdrant 검색 결과를 가져오지 못했습니다.") from exc

    results: list[ScoredChunk] = []
    try:
        for point in points:
            source = point["payload"]
            chunk = Chunk(
                chunk_id=str(source["chunk_id"]),
                document_id=str(source["document_id"]),
                index=int(source["chunk_index"]),
                text=str(source["text"]),
            )
            score = max(0.0, min(float(point["score"]), 1.0))
            results.append(ScoredChunk(chunk=chunk, keyword_score=0.0, embedding_score=score, combined_score=score))
    except (KeyError, TypeError, ValueError) as exc:
        raise QdrantError("Qdrant payload가 RAG 청크 계약과 일치하지 않습니다.") from exc
    return tuple(results)


async def sync_qdrant_index(
    *,
    chunks: tuple[Chunk, ...],
    documents_by_id: dict[str, Any],
    embedding_provider: EmbeddingProvider,
) -> int:
    """Replace approved document points with deterministic IDs."""
    vectors = await embedding_provider.embed([chunk.text for chunk in chunks])
    if not vectors or not vectors[0]:
        raise QdrantError("색인을 생성할 임베딩 벡터가 없습니다.")

    collection = _collection_url()
    try:
        async with httpx.AsyncClient(timeout=config.HEALTH_EDUCATION_TIMEOUT_SECONDS) as client:
            create = await client.put(
                collection,
                headers=_headers(),
                json={
                    "vectors": {"size": len(vectors[0]), "distance": "Cosine"},
                    "hnsw_config": {"m": 16, "ef_construct": 100},
                },
            )
            if create.status_code not in (200, 201, 409):
                create.raise_for_status()

            points = []
            for chunk, vector in zip(chunks, vectors, strict=True):
                document = documents_by_id[chunk.document_id]
                points.append(
                    {
                        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, chunk.chunk_id)),
                        "vector": vector,
                        "payload": {
                            "chunk_id": chunk.chunk_id,
                            "document_id": chunk.document_id,
                            "chunk_index": chunk.index,
                            "text": chunk.text,
                            "approved": True,
                            "checked_at": document.checked_at,
                            "source_url": document.url,
                        },
                    }
                )
            upsert = await client.put(
                f"{collection}/points",
                headers=_headers(),
                params={"wait": "true"},
                json={"points": points},
            )
            upsert.raise_for_status()
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise QdrantError("Qdrant 인덱스 동기화에 실패했습니다.") from exc
    return len(points)
