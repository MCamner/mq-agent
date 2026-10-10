"""The embedding request must be bounded by the timeout, not by the corpus size.

`build_semantic_index` collected every chunk in the corpus and passed them to
`embed` in a single call, which the Ollama provider turned into one HTTP request
with a 60 second timeout. Measured on this machine, nomic-embed-text sustains
~4.4 chunks/s, so that request could only ever carry ~264 chunks.

The failure was invisible for as long as the build was broken upstream. The
first index held 120 chunks -- under the ceiling -- because a missing Drive
token meant almost nothing was fetched. Once the token worked and more
documents came back, the build died with `embedding unavailable: TimeoutError`,
so fixing one bug surfaced the next. With the pipeline's own `max_files=500`
the chunk count reaches the thousands and a single request cannot succeed at
any timeout worth waiting on.

Batching belongs in the provider: the limit is a property of the HTTP
transport, not of the index. The `EmbeddingProvider` protocol stays
`embed(texts) -> list[list[float]]`, so the fourteen call sites that construct
this provider are unaffected.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from mq_agent.notebook_corpus_semantic import (
    DEFAULT_EMBED_BATCH_SIZE,
    OllamaEmbeddingProvider,
)


class _Response:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class FakeTransport:
    """Records each request and answers with one vector per input.

    The vector encodes the text it was produced from, so a batch reassembled in
    the wrong order is detectable rather than merely plausible.
    """

    def __init__(self) -> None:
        self.batches: list[list[str]] = []

    def __call__(self, request: Any, timeout: int | None = None) -> _Response:
        body = json.loads(request.data.decode("utf-8"))
        texts = body["input"]
        self.batches.append(list(texts))
        return _Response({"embeddings": [[float(len(t)), 1.0] for t in texts]})


@pytest.fixture
def transport(monkeypatch: pytest.MonkeyPatch) -> FakeTransport:
    fake = FakeTransport()
    monkeypatch.setattr(
        "mq_agent.notebook_corpus_semantic.urllib.request.urlopen", fake
    )
    return fake


def test_a_corpus_larger_than_one_batch_is_split(transport: FakeTransport) -> None:
    """The defect. One request for 1000 chunks cannot finish inside the timeout."""
    provider = OllamaEmbeddingProvider(batch_size=64)

    vectors = provider.embed([f"chunk-{i}" for i in range(1000)])

    assert len(vectors) == 1000
    assert len(transport.batches) > 1
    assert all(len(batch) <= 64 for batch in transport.batches)


def test_vectors_keep_input_order_across_batch_boundaries(
    transport: FakeTransport,
) -> None:
    """Order is the whole contract.

    The caller zips the returned vectors against its chunk rows, so a batching
    bug that shuffles them would attach each vector to the wrong document and
    produce an index that searches but answers wrongly -- the same silent-wrong
    class as the coverage gate.
    """
    texts = [f"chunk-{i}" + "x" * i for i in range(150)]
    provider = OllamaEmbeddingProvider(batch_size=7)

    vectors = provider.embed(texts)

    assert [v[0] for v in vectors] == [float(len(t)) for t in texts]


def test_input_within_one_batch_still_makes_one_request(
    transport: FakeTransport,
) -> None:
    provider = OllamaEmbeddingProvider(batch_size=64)

    provider.embed(["a", "b", "c"])

    assert len(transport.batches) == 1
    assert transport.batches[0] == ["a", "b", "c"]


def test_empty_input_makes_no_request(transport: FakeTransport) -> None:
    provider = OllamaEmbeddingProvider(batch_size=64)

    assert provider.embed([]) == []
    assert transport.batches == []


def test_a_bad_shape_in_a_later_batch_is_still_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validation must run per batch, not only on the first response."""
    calls = {"n": 0}

    def urlopen(request: Any, timeout: int | None = None) -> _Response:
        calls["n"] += 1
        texts = json.loads(request.data.decode("utf-8"))["input"]
        if calls["n"] == 1:
            return _Response({"embeddings": [[1.0, 1.0] for _ in texts]})
        return _Response({"embeddings": []})

    monkeypatch.setattr(
        "mq_agent.notebook_corpus_semantic.urllib.request.urlopen", urlopen
    )
    provider = OllamaEmbeddingProvider(batch_size=4)

    with pytest.raises(ValueError, match="unexpected shape"):
        provider.embed([f"chunk-{i}" for i in range(12)])


def test_batch_size_must_be_positive() -> None:
    with pytest.raises(ValueError, match="batch_size"):
        OllamaEmbeddingProvider(batch_size=0)


def test_default_batch_leaves_margin_against_the_timeout() -> None:
    """Pins the default to the measured rate rather than to taste.

    nomic-embed-text sustains ~4.4 chunks/s here for ~2000-character chunks.
    A default batch must stay well inside the default timeout, so that a slower
    machine or a larger chunk_chars does not reland the bug it fixes.
    """
    provider = OllamaEmbeddingProvider()
    measured_chunks_per_second = 4.4

    assert provider.batch_size == DEFAULT_EMBED_BATCH_SIZE
    projected = provider.batch_size / measured_chunks_per_second
    assert projected < provider.timeout / 3
