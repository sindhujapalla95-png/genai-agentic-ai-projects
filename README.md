# GenAI / Agentic AI Portfolio Projects

Production-grade sample projects showing how a data-engineering + DevOps background (Azure Data Factory, Databricks/PySpark, Delta Lake, Terraform, Azure DevOps CI/CD, Azure Monitor) translates directly into building and operating Gen AI / Agentic AI / RAG systems.

| Project | Focus | Maps to |
|---|---|---|
| [agentic-rag-pipeline](./agentic-rag-pipeline) | Event-driven Medallion (Bronze/Silver/Gold) ingestion feeding a multi-agent RAG service (Retriever -> Reasoner -> Responder), FastAPI, Docker, CI/CD | ADF orchestration, Databricks medallion architecture, Delta Lake versioning, Azure Monitor alerting |
| [agentic-devops-copilot](./agentic-devops-copilot) | Multi-agent system that reviews Terraform plans for risky changes and auto-triages/remediates failed CI/CD pipeline runs | Terraform IaC, Azure DevOps release pipelines, MTTR reduction via monitoring/alerting |

Each project is self-contained: its own requirements.txt, Dockerfile, unit tests, and GitHub Actions CI/CD workflow. See each project's README for setup and usage.

## Running tests for everything

```bash
for d in agentic-rag-pipeline agentic-devops-copilot; do
  (cd "$d" && pip install -r requirements.txt && pytest -v)
done
```
