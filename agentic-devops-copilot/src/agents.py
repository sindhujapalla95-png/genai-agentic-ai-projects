"""
Agents:

- TerraformReviewerAgent - reviews `terraform plan` JSON for risky changes
  before merge (security/cost guardrails).
- PipelineMonitorAgent   - classifies a failed pipeline run and estimates
  MTTR impact, the same signal that drove a 40% MTTR reduction via
  Azure Monitor alerting in production.
- RemediationAgent       - maps a failure classification to a known-safe
  playbook (retry / rollback / scale / manual escalation).
"""
from __future__ import annotations

from dataclasses import dataclass

from src.config import settings
from src.tools import DevOpsClient, PipelineRun, PlanFinding, TerraformPlanParser

FAILURE_PLAYBOOKS = {
    "transient_infra": "retry_with_backoff",
    "resource_conflict": "import_or_rename_resource",
    "flaky_test": "retry_stage",
    "code_regression": "block_merge_notify_owner",
    "unknown": "escalate_to_oncall",
}


@dataclass
class ReviewResult:
    approved: bool
    findings: list[PlanFinding]
    summary: str


class TerraformReviewerAgent:
    def __init__(self) -> None:
        self.parser = TerraformPlanParser()

    def run(self, plan_json: dict) -> ReviewResult:
        findings = self.parser.parse(plan_json)
        high_severity = [f for f in findings if f.severity == "high"]
        approved = len(high_severity) == 0
        summary = (
            "No risky changes detected."
            if approved
            else f"{len(high_severity)} high-severity finding(s) require review before merge."
        )
        return ReviewResult(approved=approved, findings=findings, summary=summary)


@dataclass
class FailureClassification:
    category: str
    confidence: float
    reasoning: str


class PipelineMonitorAgent:
    """Rule-based triage that mirrors the log-pattern heuristics a real
    Azure Monitor alert rule / Log Analytics query would encode."""

    _PATTERNS = (
        ("resource_conflict", ("already exists", "conflict")),
        ("transient_infra", ("timeout", "temporarily unavailable", "throttled", "429")),
        ("flaky_test", ("flaky", "intermittent", "test failed once")),
        ("code_regression", ("assertion", "typeerror", "compileerror", "syntax error")),
    )

    def run(self, run: PipelineRun) -> FailureClassification:
        log = run.log_excerpt.lower()
        for category, keywords in self._PATTERNS:
            if any(keyword in log for keyword in keywords):
                return FailureClassification(
                    category=category,
                    confidence=0.85,
                    reasoning=f"log excerpt matched '{category}' pattern",
                )
        return FailureClassification(
            category="unknown", confidence=0.3, reasoning="no known failure pattern matched"
        )

    def estimate_mttr_minutes(self, classification: FailureClassification) -> int:
        base = {
            "transient_infra": 5,
            "resource_conflict": 15,
            "flaky_test": 5,
            "code_regression": 45,
            "unknown": 60,
        }
        return base.get(classification.category, 60)


@dataclass
class RemediationPlan:
    playbook: str
    auto_executable: bool
    description: str


class RemediationAgent:
    def run(self, classification: FailureClassification) -> RemediationPlan:
        playbook = FAILURE_PLAYBOOKS.get(classification.category, "escalate_to_oncall")
        auto_executable = playbook in {"retry_with_backoff", "retry_stage"}
        description = {
            "retry_with_backoff": "Transient infra issue - retrying stage with exponential backoff.",
            "import_or_rename_resource": "Resource address conflict - needs a terraform import "
            "or address rename; opening a PR comment for a human to resolve.",
            "retry_stage": "Likely flaky test - retrying the stage once automatically.",
            "block_merge_notify_owner": "Code regression suspected - blocking merge and "
            "notifying the pipeline owner.",
            "escalate_to_oncall": "Unrecognized failure pattern - escalating to on-call for triage.",
        }[playbook]
        return RemediationPlan(playbook=playbook, auto_executable=auto_executable, description=description)


class DevOpsOrchestratorAgents:
    """Convenience bundle wiring the three agents to a shared DevOps client,
    used by src/orchestrator.py's event router."""

    def __init__(self, client: DevOpsClient | None = None) -> None:
        self.client = client or DevOpsClient()
        self.reviewer = TerraformReviewerAgent()
        self.monitor = PipelineMonitorAgent()
        self.remediator = RemediationAgent()
