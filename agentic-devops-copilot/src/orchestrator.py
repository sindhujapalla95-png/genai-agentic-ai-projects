"""
Event-driven orchestrator: routes inbound events (webhook payloads) to the
appropriate agent, the same declarative trigger -> activity mapping used
for parameterized, reusable ADF/Azure DevOps pipeline templates.
"""
from __future__ import annotations

from dataclasses import asdict

from src.agents import DevOpsOrchestratorAgents
from src.tools import PipelineRun


class Orchestrator:
    def __init__(self, agents: DevOpsOrchestratorAgents | None = None) -> None:
        self.agents = agents or DevOpsOrchestratorAgents()

    def review_terraform_plan(self, plan_json: dict, pull_request_id: str | None = None) -> dict:
        result = self.agents.reviewer.run(plan_json)
        if pull_request_id and not result.approved:
            comment = "Agentic DevOps Copilot flagged the following before merge:\n" + "\n".join(
                f"- [{f.severity}] {f.rule} on `{f.resource_address}`" for f in result.findings
            )
            self.agents.client.post_comment(pull_request_id, comment)
        return {
            "approved": result.approved,
            "summary": result.summary,
            "findings": [asdict(f) for f in result.findings],
        }

    def handle_pipeline_event(self, event: dict) -> dict:
        run = PipelineRun(
            pipeline=event["pipeline"],
            status=event["status"],
            stage=event.get("stage", "unknown"),
            log_excerpt=event.get("log_excerpt", ""),
        )

        if run.status != "failed":
            return {"handled": False, "reason": "only failed runs are triaged"}

        classification = self.agents.monitor.run(run)
        mttr_estimate = self.agents.monitor.estimate_mttr_minutes(classification)
        plan = self.agents.remediator.run(classification)

        return {
            "handled": True,
            "classification": {
                "category": classification.category,
                "confidence": classification.confidence,
                "reasoning": classification.reasoning,
            },
            "estimated_mttr_minutes": mttr_estimate,
            "remediation": {
                "playbook": plan.playbook,
                "auto_executable": plan.auto_executable,
                "description": plan.description,
            },
        }
