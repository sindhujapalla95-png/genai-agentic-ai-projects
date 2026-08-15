"""
Tool layer: Terraform plan parsing + a mockable Azure DevOps API client.

Kept dependency-light and fully offline-testable: the DevOps client talks to
the real REST API only when a PAT is configured, otherwise it returns
deterministic mock data so the agents/orchestrator can be exercised in CI.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings


def _after_state(change: dict) -> dict:
    return (change.get("change") or {}).get("after") or {}


RISKY_PATTERNS = {
    "public_ingress": lambda after: str(after.get("source_address_prefix", "")) == "0.0.0.0/0"
    or "0.0.0.0/0" in str(after.get("cidr_blocks", "")),
    "encryption_disabled": lambda after: after.get("encryption_enabled") is False
    or after.get("enabled") is False
    and "encryption" in str(after).lower(),
    "oversized_sku": lambda after: any(
        str(after.get("sku_name", after.get("sku", ""))).startswith(prefix)
        for prefix in ("Standard_M", "Standard_GS", "Standard_ND")
    ),
    "public_storage_access": lambda after: after.get("allow_blob_public_access") is True,
}


@dataclass
class PlanFinding:
    resource_address: str
    rule: str
    severity: str
    detail: str


class TerraformPlanParser:
    """Parses a `terraform show -json plan.out` style document for risky diffs."""

    def parse(self, plan_json: dict) -> list[PlanFinding]:
        findings: list[PlanFinding] = []
        for change in plan_json.get("resource_changes", []):
            address = change.get("address", "unknown")
            after = _after_state(change)
            for rule_name, matcher in RISKY_PATTERNS.items():
                if matcher(after):
                    findings.append(
                        PlanFinding(
                            resource_address=address,
                            rule=rule_name,
                            severity="high" if rule_name != "oversized_sku" else "medium",
                            detail=f"{rule_name} pattern matched on {address}",
                        )
                    )
        return findings


@dataclass
class PipelineRun:
    pipeline: str
    status: str
    stage: str
    log_excerpt: str


@dataclass
class DevOpsClient:
    """Thin Azure DevOps REST wrapper with retry + offline mock fallback."""

    org: str | None = field(default_factory=lambda: settings.azure_devops_org)
    project: str | None = field(default_factory=lambda: settings.azure_devops_project)
    pat: str | None = field(default_factory=lambda: settings.azure_devops_pat)

    def _live(self) -> bool:
        return bool(self.org and self.project and self.pat)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5))
    def get_recent_failed_runs(self, pipeline: str, limit: int = 5) -> list[PipelineRun]:
        if not self._live():
            return [
                PipelineRun(
                    pipeline=pipeline,
                    status="failed",
                    stage="terraform-apply",
                    log_excerpt="Error: A resource with the ID already exists - "
                    "must import or change resource address",
                )
            ][:limit]

        url = (
            f"https://dev.azure.com/{self.org}/{self.project}/_apis/pipelines/"
            f"{pipeline}/runs?api-version=7.1"
        )
        response = requests.get(
            url, auth=("", self.pat), timeout=settings.request_timeout_s
        )
        response.raise_for_status()
        runs = response.json().get("value", [])[:limit]
        return [
            PipelineRun(
                pipeline=pipeline,
                status=r.get("result", "unknown"),
                stage=r.get("stage", "unknown"),
                log_excerpt=r.get("logExcerpt", ""),
            )
            for r in runs
        ]

    def post_comment(self, pull_request_id: str, comment: str) -> dict:
        if not self._live():
            return {"status": "mocked", "pull_request_id": pull_request_id, "comment": comment}

        url = (
            f"https://dev.azure.com/{self.org}/{self.project}/_apis/git/pullrequests/"
            f"{pull_request_id}/threads?api-version=7.1"
        )
        payload = {"comments": [{"parentCommentId": 0, "content": comment, "commentType": 1}]}
        response = requests.post(
            url, auth=("", self.pat), json=payload, timeout=settings.request_timeout_s
        )
        response.raise_for_status()
        return response.json()
