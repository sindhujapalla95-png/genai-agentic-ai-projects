"""Unit tests for the medallion pipeline and agent orchestration."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.agents import AgentOrchestrator  # noqa: E402
from src.data_pipeline import MedallionPipeline  # noqa: E402
from src.vector_store import VectorStore  # noqa: E402


def _fresh_store() -> VectorStore:
    return VectorStore(index_path="./data/test_index")


def test_bronze_deduplicates_identical_content():
    store = _fresh_store()
    pipeline = MedallionPipeline(store)

    first = pipeline.run("doc1.txt", "Retry policy: exponential backoff, 3 attempts.")
    second = pipeline.run("doc1_copy.txt", "Retry policy: exponential backoff, 3 attempts.")

    assert first["status"] == "ok"
    assert second["status"] == "skipped_duplicate"


def test_medallion_pipeline_publishes_chunks():
    store = _fresh_store()
    pipeline = MedallionPipeline(store)

    result = pipeline.run("doc2.txt", "The ingestion pipeline runs on an event-driven trigger. " * 20)

    assert result["status"] == "ok"
    assert result["chunks_published"] > 0


def test_orchestrator_returns_grounded_answer_with_context():
    store = _fresh_store()
    pipeline = MedallionPipeline(store)
    pipeline.run("doc3.txt", "The SLA for pipeline reliability is 99.9 percent uptime.")

    orchestrator = AgentOrchestrator(store)
    response = orchestrator.handle("What is the SLA for pipeline reliability?")

    assert response["answer"] is not None
    assert len(response["citations"]) > 0
    assert "retriever" in response["trace"][0]


def test_orchestrator_handles_empty_index_gracefully():
    store = _fresh_store()
    orchestrator = AgentOrchestrator(store)

    response = orchestrator.handle("Anything in the index?")

    assert "don't have enough" in response["answer"]
    assert response["citations"] == []
