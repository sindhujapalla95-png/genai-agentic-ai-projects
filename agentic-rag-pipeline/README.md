# Agentic RAG Pipeline

Production-grade, event-driven Retrieval-Augmented Generation (RAG) platform that combines a Medallion-architecture data pipeline (Bronze -> Silver -> Gold) with a multi-agent orchestration layer for enterprise document Q&A.

This project mirrors the data-engineering-to-GenAI pattern used in production: the same trigger-based orchestration, context-engineering, secrets management, and SLA/monitoring discipline used to run large-scale Azure Data Factory / Databricks pipelines is applied here to a RAG + agentic AI system.

## Getting started

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn src.api:app --reload
```

See source files for full architecture (Medallion Bronze/Silver/Gold pipeline, multi-agent RAG orchestration, monitoring/alerting).

## License

MIT
