from dataclasses import dataclass
from datetime import datetime, timezone

import chromadb

from aime.utils.text_chunker import chunk_text


@dataclass
class MemoryResult:
    chroma_id: str
    content: str
    distance: float
    metadata: dict


class MemoryLayer:
    def __init__(self, chroma_client: chromadb.PersistentClient):
        self.chroma = chroma_client

    def get_collection(self, entity_id: str) -> chromadb.Collection:
        return self.chroma.get_or_create_collection(
            name=f"entity_{entity_id}",
            metadata={"hnsw:space": "cosine"},
        )

    def ingest(
        self,
        entity_id: str,
        feed_id: str,
        text: str,
        source_label: str | None = None,
    ) -> int:
        """Chunk text, embed, store in ChromaDB. Returns chunk count."""
        chunks = chunk_text(text, max_tokens=500, overlap=50)
        if not chunks:
            return 0

        collection = self.get_collection(entity_id)
        ids = []
        documents = []
        metadatas = []

        for chunk in chunks:
            chunk_id = f"{feed_id}_{chunk.index}"
            ids.append(chunk_id)
            documents.append(chunk.text)
            metadatas.append({
                "entity_id": entity_id,
                "feed_id": feed_id,
                "chunk_index": chunk.index,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_label": source_label or "",
                "token_count": chunk.token_count,
            })

        collection.add(ids=ids, documents=documents, metadatas=metadatas)
        return len(chunks)

    def recall(
        self,
        entity_id: str,
        query: str,
        n_results: int = 5,
    ) -> list[MemoryResult]:
        """Retrieve relevant memories via semantic search."""
        collection = self.get_collection(entity_id)
        if collection.count() == 0:
            return []

        n = min(n_results, collection.count())
        results = collection.query(
            query_texts=[query],
            n_results=n,
            include=["documents", "metadatas", "distances"],
        )

        return [
            MemoryResult(
                chroma_id=results["ids"][0][i],
                content=results["documents"][0][i],
                distance=results["distances"][0][i],
                metadata=results["metadatas"][0][i],
            )
            for i in range(len(results["ids"][0]))
        ]

    def get_recent(
        self,
        entity_id: str,
        limit: int = 20,
    ) -> list[str]:
        """Get recent memories for summary/fusion eval."""
        collection = self.get_collection(entity_id)
        if collection.count() == 0:
            return []

        n = min(limit, collection.count())
        results = collection.get(
            include=["documents", "metadatas"],
            limit=n,
        )

        if not results["documents"]:
            return []

        # Sort by timestamp descending
        paired = sorted(
            zip(results["documents"], results["metadatas"]),
            key=lambda x: x[1].get("timestamp", ""),
            reverse=True,
        )
        return [doc for doc, _ in paired]

    def get_stats(self, entity_id: str) -> dict:
        """Get memory layer statistics."""
        collection = self.get_collection(entity_id)
        count = collection.count()
        return {
            "total_entries": count,
            "structured_ratio": min(1.0, count * 0.05) if count > 0 else 0,
        }
