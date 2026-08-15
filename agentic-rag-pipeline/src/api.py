"""FastAPI service exposing ingestion and query endpoints."""
from __future__ import annotations

from fastapi import FastAPI, File, UploadFile
from pydantic import BaseModel

from src.agents import AgentOrchestrator
from src.data_pipeline import MedallionPipeline
from src.monitoring import metrics
from src.vector_store import VectorStore

app = FastAPI(
    title="Agentic RAG Pipeline",
    description="Event-driven, medallion-architecture RAG service with multi-agent orchestration.",
    version="1.0.0",
)

vector_store = VectorStore()
pipeline = MedallionPipeline(vector_store)
orchestrator = AgentOrchestrator(vector_store)


class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    answer: str | None
    citations: list[str]
    trace: list[str]


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/metrics")
def get_metrics() -> dict:
    return metrics.snapshot()


@app.post("/ingest")
async def ingest(file: UploadFile = File(...)) -> dict:
    raw_bytes = await file.read()
    text = raw_bytes.decode("utf-8", errors="ignore")
    result = pipeline.run(source_path=file.filename, raw_text=text)
    return result


@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    result = orchestrator.handle(request.question)
    return QueryResponse(**result)
