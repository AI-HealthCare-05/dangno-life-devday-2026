from __future__ import annotations

import argparse
import asyncio

from src.rag.embeddings import get_embedding_provider
from src.rag.engine import ALL_CHUNKS, DOCUMENTS_BY_ID
from src.rag.qdrant import sync_qdrant_index


async def _sync() -> None:
    count = await sync_qdrant_index(
        chunks=ALL_CHUNKS,
        documents_by_id=DOCUMENTS_BY_ID,
        embedding_provider=get_embedding_provider(),
    )
    print(f"Indexed {count} approved RAG chunks.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage the approved health-education vector index.")
    parser.add_argument("command", choices=("sync",))
    args = parser.parse_args()
    if args.command == "sync":
        asyncio.run(_sync())


if __name__ == "__main__":
    main()
