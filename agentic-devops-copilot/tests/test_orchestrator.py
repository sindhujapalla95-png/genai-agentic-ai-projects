"""Unit tests for the Terraform review and pipeline-triage agents."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.orchestrator import Orchestrator  # noqa: E402

SAFE_PLAN = {
    "resource_changes": [
        {
            "address": "azurerm_storage_account.data",
            "change": {"after": {"allow_blob_public_access": False}},
        }
    ]
}

RISKY_PLAN = {
    "resource_changes": [
        {
            "address": "azurerm_network_security_rule.allow_all",
            "change": {"after": {"source_address_prefix": "0.0.0.0/0"}},
        },
        {
            "address": "azurerm_storage_account.public",
            "change": {"after": {"allow_blob_public_access": True}},
        },
    ]
}


def test_safe_plan_is_approved():
    orchestrator = Orchestrator()
    result = orchestrator.review_terraform_plan(SAFE_PLAN)
    assert result["approved"] is True
    assert result["findings"] == []


def test_risky_plan_is_blocked_and_findings_reported():
    orchestrator = Orchestrator()
    result = orchestrator.review_terraform_plan(RISKY_PLAN, pull_request_id="123")
    assert result["approved"] is False
    assert len(result["findings"]) >= 2


def test_transient_failure_is_classified_and_auto_remediated():
    orchestrator = Orchestrator()
    event = {
        "pipeline": "data-platform-ci",
        "status": "failed",
        "stage": "terraform-apply",
        "log_excerpt": "Request throttled: 429 Too Many Requests",
    }
    result = orchestrator.handle_pipeline_event(event)

    assert result["handled"] is True
    assert result["classification"]["category"] == "transient_infra"
    assert result["remediation"]["auto_executable"] is True


def test_code_regression_blocks_merge_and_notifies():
    orchestrator = Orchestrator()
    event = {
        "pipeline": "api-ci",
        "status": "failed",
        "stage": "unit-tests",
        "log_excerpt": "AssertionError: expected 200 got 500",
    }
    result = orchestrator.handle_pipeline_event(event)

    assert result["classification"]["category"] == "code_regression"
    assert result["remediation"]["playbook"] == "block_merge_notify_owner"
    assert result["remediation"]["auto_executable"] is False


def test_successful_run_is_not_triaged():
    orchestrator = Orchestrator()
    event = {"pipeline": "api-ci", "status": "succeeded"}
    result = orchestrator.handle_pipeline_event(event)
    assert result["handled"] is False
