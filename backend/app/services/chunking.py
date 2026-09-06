import re


def normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 150) -> list[str]:
    """Split text into ~chunk_size character windows with ~overlap character
    overlap, preferring to break on whitespace near the boundary so chunks
    don't split mid-word.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    n = len(text)

    while start < n:
        end = min(start + chunk_size, n)

        if end < n:
            boundary = text.rfind(" ", start + int(chunk_size * 0.5), end)
            if boundary != -1:
                end = boundary

        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)

        if end >= n:
            break

        next_start = max(end - overlap, start + 1)
        # Align the overlap to a word boundary too, so the next chunk does not
        # begin mid-token and embed a meaningless fragment.
        if next_start > 0 and not text[next_start - 1].isspace():
            boundary = text.rfind(" ", start, next_start)
            if boundary != -1 and boundary + 1 > start:
                next_start = boundary + 1
        start = next_start

    return chunks
