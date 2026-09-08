"""An exact fetch approval clears only the public-destination prompt."""
from dataclasses import replace

import pytest

from copenet.core.tools.barricade import approval_key, get_security_state, pre_dispatch_gate, reset_session_security
from copenet.core.tools.contracts import ToolExecutionContext, ToolExecutionRequest
from copenet.core.tools.policy import ToolPolicy


@pytest.fixture
def context(tmp_path, monkeypatch):
    monkeypatch.setenv("COPENET_BARRICADE", "1")
    monkeypatch.delenv("COPNET_WEB_FETCH_ALLOWLIST", raising=False)
    reset_session_security("fetch-approval")
    yield ToolExecutionContext(
        workdir=tmp_path, session_workspace_root=tmp_path, session_key="fetch-approval",
        provider_name="test", model=None, session_store=None, transcript_store=None,
        providers={}, policy=ToolPolicy(),
    )
    reset_session_security("fetch-approval")


def test_fetch_approval_covers_only_exact_arguments_in_current_run(context):
    request = ToolExecutionRequest("web.fetch", {"url": "https://example.com/announcement", "maxChars": 1000})
    assert pre_dispatch_gate(request, context).output["policyDecision"] == "approval_required"
    context.ephemeral["barricade_approved"] = {approval_key(request)}
    assert pre_dispatch_gate(request, context) is None
    assert get_security_state(context).events[-1].kind == "egress_allowed"
    for args in ({"url": "https://example.com/other", "maxChars": 1000},
                 {"url": "https://example.com/announcement", "maxChars": 2000}):
        assert pre_dispatch_gate(ToolExecutionRequest("web.fetch", args), context).output["policyDecision"] == "approval_required"
    assert pre_dispatch_gate(request, replace(context, ephemeral={})).output["policyDecision"] == "approval_required"


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/private", "file:///private", "https://example.com/?token=synthetic",
    "https://example.com/synthetic_canary_123456",
])
def test_fetch_approval_never_bypasses_hard_egress_checks(context, url):
    request = ToolExecutionRequest("web.fetch", {"url": url})
    context.ephemeral["barricade_approved"] = {approval_key(request)}
    get_security_state(context).sensitive_values.append("synthetic_canary_123456")
    assert pre_dispatch_gate(request, context).output["policyDecision"] == "egress_blocked"
