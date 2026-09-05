from app.services.chunking import chunk_text, normalize


def test_normalize_collapses_whitespace_and_crlf():
    raw = "Hello\r\nworld\r\n\r\n\r\nfoo   bar\t\tbaz"
    result = normalize(raw)
    assert "\r" not in result
    assert "\n\n\n" not in result
    assert "foo bar baz" in result


def test_short_text_is_a_single_chunk():
    text = "Short document body."
    chunks = chunk_text(text, chunk_size=1000, overlap=150)
    assert chunks == [text]


def test_empty_text_produces_no_chunks():
    assert chunk_text("", chunk_size=1000, overlap=150) == []
    assert chunk_text("   ", chunk_size=1000, overlap=150) == []


def test_long_text_is_split_into_multiple_chunks_with_overlap():
    # Unique tokens make it possible to check exactly which tokens two
    # consecutive chunks share, rather than guessing at substring overlap.
    tokens = [f"tok{i:04d}" for i in range(800)]
    text = " ".join(tokens)  # ~7200 chars
    chunks = chunk_text(text, chunk_size=1000, overlap=150)

    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= 1000

    for first, second in zip(chunks, chunks[1:]):
        first_tokens = set(first.split())
        second_tokens = set(second.split())
        shared = first_tokens & second_tokens
        assert shared, "consecutive chunks must share at least one overlapping token"


def test_chunking_covers_the_whole_document():
    tokens = [f"tok{i:04d}" for i in range(800)]
    text = " ".join(tokens)
    chunks = chunk_text(text, chunk_size=1000, overlap=150)

    covered_tokens: set[str] = set()
    for c in chunks:
        covered_tokens.update(c.split())

    assert covered_tokens == set(tokens), "chunking must not drop any content"
