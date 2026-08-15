# Agentic DevOps Copilot

A multi-agent AI system that watches CI/CD pipelines, reviews Infrastructure-as-Code changes, and proposes/executes remediation. Pairs a classical DevOps/SRE toolchain (Terraform + Azure DevOps + Azure Monitor) with LLM agents.

This project takes the same primitives used to run production release pipelines (IaC review, zero-downtime deployment, monitoring/alerting, MTTR reduction) and wraps them in autonomous agents that reason over pipeline telemetry and Terraform plans.

## Why this design

| Production DevOps practice | Applied here as |
|---|---|
| Terraform IaC across Dev/QA/Prod | `TerraformReviewerAgent` parses `terraform plan` JSON and flags risky diffs (public ingress, disabled encryption, oversized SKUs) before merge |
| Zero-downtime Azure DevOps release pipelines | `PipelineMonitorAgent` consumes pipeline run events and classifies failures (flaky test vs. infra vs. code regression) |
| Azure Monitor alerting, 40% MTTR reduction | `RemediationAgent` maps failure classes to known-safe playbooks (retry, rollback, scale) and reports an MTTR estimate |
| Reusable, parameterized pipeline templates | `Orchestrator` is a declarative, event-to-agent routing table for new event types |
| Azure Key Vault secrets management | `src/config.py` resolves all tokens/PATs from environment only |

## Getting started

```bash
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...          # optional, falls back to rule-based review offline
export AZURE_DEVOPS_PAT=...           # optional, required only for live pipeline calls

uvicorn src.api:app --reload
```

Simulate a Terraform PR review:

```bash
curl -X POST localhost:8000/review/terraform -H "Content-Type: application/json" -d @examples/sample_plan.json
```

Simulate a failed pipeline event:

```bash
curl -X POST localhost:8000/events/pipeline -H "Content-Type: application/json" -d '{"pipeline": "data-platform-ci", "status": "failed", "stage": "terraform-apply", "log_excerpt": "Error: A resource with the ID already exists"}'
```

## Running with Docker

```bash
docker build -t agentic-devops-copilot .
docker run -p 8000:8000 --env-file .env agentic-devops-copilot
```

## Tests

```bash
pytest -v
```

## License

MIT
