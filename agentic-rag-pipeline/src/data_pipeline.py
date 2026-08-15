"""
Medallion-style ingestion pipeline: Bronze -> Silver -> Gold.

This is the context-engineering layer that feeds the RAG/agent system,
modeled directly on a PySpark/Databricks medallion pipeline:

  Bronze  - raw documents landed as-is, content-hashed for idempotent,
            trigger-based re-runs (no duplicate ingestion on retry).
  Silver  - cleaned, normalized, chunked text ready for embedding.
  Gold    - embedded vectors + metadata, retrieval-ready.

Each stage is independently retryable and instrumented, mirroring the
dependency/parameterization model used for production ADF pipelines.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings
from src.monitoring import timed


@dataclass
class RawDocument:
    doc_id: str
    source_path: str
    text: str
    content_hash: str


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    text: str
    position: int


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class BronzeStage:
    """Land raw documents unmodified, deduplicated by content hash."""

    def __init__(self) -> None:
        self._seen_hashes: set[str] = set()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5))
    def ingest(self, source_path: str, raw_text: str) -> RawDocument | None:
        with timed("bronze.ingest", source=source_path):
            content_hash = _hash(raw_text)
            if content_hash in self._seen_hashes:
                return None
            self._seen_hashes.add(content_hash)
            doc_id = f"doc_{content_hash}"
            return RawDocument(
                doc_id=doc_id,
                source_path=source_path,
                text=raw_text,
                content_hash=content_hash,
            )


class SilverStage:
    """Clean + chunk raw text into retrieval-ready windows."""

    def __init__(self, chunk_size: int | None = None, chunk_overlap: int | None = None) -> None:
        self.chunk_size = chunk_size or settings.chunk_size
        self.chunk_overlap = chunk_overlap or settings.chunk_overlap

    @staticmethod
    def _clean(text: str) -> str:
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def chunk(self, document: RawDocument) -> list[Chunk]:
        with timed("silver.chunk", doc_id=document.doc_id):
            clean_text = self._clean(document.text)
            step = max(self.chunk_size - self.chunk_overlap, 1)
            chunks: list[Chunk] = []
            position = 0
            for i, start in enumerate(range(0, len(clean_text), step)):
                window = clean_text[start : start + self.chunk_size]
                if not window:
                    continue
                chunks.append(
                    Chunk(
                        chunk_id=f"{document.doc_id}_c{i}",
                        doc_id=document.doc_id,
                        text=window,
                        position=position,
                    )
                )
                position += 1
                if start + self.chunk_size >= len(clean_text):
                    break
            return chunks


class GoldStage:
    """Embed silver-layer chunks into the vector store (see vector_store.py)."""

    def __init__(self, vector_store) -> None:
        self.vector_store = vector_store

    def publish(self, chunks: list[Chunk]) -> int:
        with timed("gold.publish", chunk_count=len(chunks)):
            self.vector_store.add_chunks(chunks)
            return len(chunks)


class MedallionPipeline:
    """Orchestrates Bronze -> Silver -> Gold, with per-stage retry/telemetry."""

    def __init__(self, vector_store) -> None:
        self.bronze = BronzeStage()
        self.silver = SilverStage()
        self.gold = GoldStage(vector_store)

    def run(self, source_path: str, raw_text: str) -> dict:
        document = self.bronze.ingest(source_path, raw_text)
        if document is None:
            return {"status": "skipped_duplicate", "source": source_path}

        chunks = self.silver.chunk(document)
        published = self.gold.publish(chunks)
        return {
            "status": "ok",
            "doc_id": document.doc_id,
            "chunks_published": published,
        }

    def run_directory(self, directory: str) -> list[dict]:
        results = []
        for path in sorted(Path(directory).glob("**/*.txt")):
            results.append(self.run(str(path), path.read_text(encoding="utf-8")))
        return results
