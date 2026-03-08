from dataclasses import dataclass

import tiktoken


@dataclass
class Chunk:
    text: str
    token_count: int
    index: int


_enc = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_enc.encode(text))


def chunk_text(text: str, max_tokens: int = 500, overlap: int = 50) -> list[Chunk]:
    """Split text into chunks by paragraphs, then sentences if needed."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [text.strip()]

    chunks: list[Chunk] = []
    current_parts: list[str] = []
    current_tokens = 0

    for para in paragraphs:
        para_tokens = count_tokens(para)

        if para_tokens > max_tokens:
            # Flush current buffer first
            if current_parts:
                combined = "\n\n".join(current_parts)
                chunks.append(Chunk(text=combined, token_count=count_tokens(combined), index=len(chunks)))
                current_parts = []
                current_tokens = 0
            # Split long paragraph by sentences
            sentences = _split_sentences(para)
            sent_buf: list[str] = []
            sent_tokens = 0
            for sent in sentences:
                st = count_tokens(sent)
                if sent_tokens + st > max_tokens and sent_buf:
                    combined = " ".join(sent_buf)
                    chunks.append(Chunk(text=combined, token_count=count_tokens(combined), index=len(chunks)))
                    # Keep overlap
                    overlap_sents = []
                    overlap_t = 0
                    for s in reversed(sent_buf):
                        ot = count_tokens(s)
                        if overlap_t + ot > overlap:
                            break
                        overlap_sents.insert(0, s)
                        overlap_t += ot
                    sent_buf = overlap_sents
                    sent_tokens = overlap_t
                sent_buf.append(sent)
                sent_tokens += st
            if sent_buf:
                combined = " ".join(sent_buf)
                chunks.append(Chunk(text=combined, token_count=count_tokens(combined), index=len(chunks)))
        elif current_tokens + para_tokens > max_tokens and current_parts:
            combined = "\n\n".join(current_parts)
            chunks.append(Chunk(text=combined, token_count=count_tokens(combined), index=len(chunks)))
            current_parts = [para]
            current_tokens = para_tokens
        else:
            current_parts.append(para)
            current_tokens += para_tokens

    if current_parts:
        combined = "\n\n".join(current_parts)
        chunks.append(Chunk(text=combined, token_count=count_tokens(combined), index=len(chunks)))

    # Re-index
    for i, c in enumerate(chunks):
        c.index = i

    return chunks if chunks else [Chunk(text=text.strip(), token_count=count_tokens(text), index=0)]


def _split_sentences(text: str) -> list[str]:
    """Simple sentence splitter for Chinese and English."""
    import re
    parts = re.split(r'(?<=[。！？.!?])\s*', text)
    return [p.strip() for p in parts if p.strip()]
