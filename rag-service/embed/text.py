"""Provider-neutral chunking, kept separate from inference configuration."""


def chunk_text(text: str, chunk_size: int = 512, overlap: int = 50) -> list[str]:
    if chunk_size <= 0 or not 0 <= overlap < chunk_size:
        raise ValueError("overlap must be nonnegative and less than chunk_size")
    chunks = []
    for start in range(0, len(text), chunk_size - overlap):
        chunk = text[start:start + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
        if start + chunk_size >= len(text):
            break
    return chunks
