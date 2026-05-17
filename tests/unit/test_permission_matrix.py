import pytest

from copenet.probes.permission_matrix import run_permission_matrix


@pytest.mark.asyncio
async def test_permission_matrix_distinguishes_default_and_full_access(tmp_path):
    rows = await run_permission_matrix(workspace=tmp_path)

    by_key = {(row.task_mode, row.probe): row for row in rows}
    assert all(row.passed for row in rows)
    assert by_key[("none", "shell_syntax_pipe")].ok is False
    assert by_key[("none", "repo_write_tool")].policy_decision == "write_blocked"
    assert by_key[("full-access", "shell_syntax_pipe")].ok is True
    assert by_key[("full-access", "shell_syntax_pipe")].stdout_preview == "HI"
    assert by_key[("full-access", "repo_write_tool")].ok is True
    assert by_key[("full-access", "high_risk_shell_approval")].policy_decision == "approval_required"
    assert by_key[("full-access", "repo_mutation_approval")].policy_decision == "approval_required"
