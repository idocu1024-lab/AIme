from sqlalchemy.ext.asyncio import AsyncSession

from aime.deps import get_chroma
from aime.core.memory_layer import MemoryLayer
from aime.models.entity import Entity
from aime.models.feed import Feed


async def process_feed(
    entity: Entity,
    text: str,
    source_label: str | None,
    db: AsyncSession,
) -> Feed:
    """Ingest text feed: create Feed record, chunk and store in ChromaDB."""
    feed = Feed(
        entity_id=entity.id,
        raw_text=text,
        source_label=source_label,
    )
    db.add(feed)
    await db.flush()  # Get the feed.id

    memory = MemoryLayer(get_chroma())
    chunk_count = memory.ingest(
        entity_id=entity.id,
        feed_id=feed.id,
        text=text,
        source_label=source_label,
    )

    feed.chunk_count = chunk_count
    feed.processed = True
    entity.total_feeds += 1

    await db.commit()
    await db.refresh(feed)
    return feed
