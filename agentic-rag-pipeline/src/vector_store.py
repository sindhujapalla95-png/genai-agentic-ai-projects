"""
Embedding + similarity search layer (the "Gold" retrieval index).

Uses FAISS for local, dependency-light vector search. The embedding call is
abstracted behind `Embedder` so the OpenAI client can be swapped for any
provider (Azure OpenAI, local sentence-transformers, etc.) without touching
the retrieval logic.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

import numpy as np

from src.config import settings
from src.monitoring import timed


@dataclass
class SearchResult:
    chunk_id: str
    doc_id: str
    text: str
    score: float


class Embedder:
    """Thin wrapper around the embeddings API with a deterministic offline fallback."""

    def __init__(self, model: str | None = None) -> None:
        self.model = model or settings.embedding_model
        self._client = None
        if settings.openai_api_key:
            from openai import OpenAI

            self._client = OpenAI(api_key=settings.openai_api_key)

    def embed(self, texts: list[str]) -> np.ndarray:
        with timed("embedder.embed", batch_size=len(texts)):
            if self._client is not None:
                response = self._client.embeddings.create(model=self.model, input=texts)
                vectors = [item.embedding for item in response.data]
                return np.array(vectors, dtype="float32")
            return np.array([self._hash_embedding(t) for t in texts], dtype="float32")

    @staticmethod
    def _hash_embedding(text: str, dim: int = 256) -> list[float]:
        rng = np.random.default_rng(abs(hash(text)) % (2**32))
        vec = rng.normal(size=dim)
        return (vec / np.linalg.norm(vec)).tolist()


class VectorStore:
    """FAISS-backed cosine-similarity store with JSON metadata sidecar."""

    def __init__(self, index_path: str | None = None, embedder: Embedder | None = None) -> None:
        import faiss

        self.index_path = index_path or settings.vector_store_path
        self.embedder = embedder or Embedder()
        self._faiss = faiss
        self._index = None
        self._metadata: list[dict] = []
        self._dim: int | None = None

    def _ensure_index(self, dim: int) -> None:
        if self._index is None:
            self._index = self._faiss.IndexFlatIP(dim)
            self._dim = dim

    def add_chunks(self, chunks) -> None:
        if not chunks:
            return
        vectors = self.embedder.embed([c.text for c in chunks])
        faiss_normalize = self._faiss.normalize_L2
        faiss_normalize(vectors)
        self._ensure_index(vectors.shape[1])
        self._index.add(vectors)
        self._metadata.extend(
            {"chunk_id": c.chunk_id, "doc_id": c.doc_id, "text": c.text} for c in chunks
        )

    def search(self, query: str, top_k: int | None = None) -> list[SearchResult]:
        with timed("vector_store.search", query_len=len(query)):
            if self._index is None or self._index.ntotal == 0:
                return []
            top_k = top_k or settings.top_k
            query_vec = self.embedder.embed([query])
            self._faiss.normalize_L2(query_vec)
            scores, indices = self._index.search(query_vec, min(top_k, self._index.ntotal))
            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx == -1:
                    continue
                meta = self._metadata[idx]
                results.append(
                    SearchResult(
                        chunk_id=meta["chunk_id"],
                        doc_id=meta["doc_id"],
                        text=meta["text"],
                        score=float(score),
                    )
                )
            return results

    def persist(self, path: str | None = None) -> None:
        path = path or self.index_path
        os.makedirs(path, exist_ok=True)
        if self._index is not None:
            self._faiss.write_index(self._index, os.path.join(path, "index.faiss"))
        with open(os.path.join(path, "metadata.json"), "w", encoding="utf-8") as fh:
            json.dump(self._metadata, fh)

    def load(self, path: str | None = None) -> None:
        path = path or self.index_path
        index_file = os.path.join(path, "index.faiss")
        meta_file = os.path.join(path, "metadata.json")
        if os.path.exists(index_file):
            self._index = self._faiss.read_index(index_file)
        if os.path.exists(meta_file):
            with open(meta_file, encoding="utf-8") as fh:
                self._metadata = json.load(fh)
