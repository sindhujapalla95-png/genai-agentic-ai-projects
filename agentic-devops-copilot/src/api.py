"""FastAPI webhook receiver for the Agentic DevOps Copilot."""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from src.orchestrator import Orchestrator

app = FastAPI(
    title="Agentic DevOps Copilot",
    description="Multi-agent Terraform review + pipeline failure triage/remediation.",
    version="1.0.0",
)

orchestrator = Orchestrator()


class PipelineEvent(BaseModel):
    pipeline: str
    status: str
    stage: str = "unknown"
    log_excerpt: str = ""


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/review/terraform")
def review_terraform(plan_json: dict, pull_request_id: str | None = None) -> dict:
    return orchestrator.review_terraform_plan(plan_json, pull_request_id=pull_request_id)


@app.post("/events/pipeline")
def pipeline_event(event: PipelineEvent) -> dict:
    return orchestrator.handle_pipeline_event(event.model_dump())
