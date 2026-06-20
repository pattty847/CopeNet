from pathlib import Path

import pytest

from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.core.tools import ToolExecutionContext, ToolExecutionRequest, ToolPolicy, ToolRegistry, policy_for_task_mode


def _context(tmp_path: Path) -> ToolExecutionContext:
    return _context_with_policy(tmp_path, ToolPolicy(shell_allowlist=("grep", "pwd")))


def _context_with_policy(tmp_path: Path, policy: ToolPolicy) -> ToolExecutionContext:
    return ToolExecutionContext(
        workdir=tmp_path,
        session_workspace_root=tmp_path,
        session_key="alpha",
        provider_name="test",
        model=None,
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "history"),
        providers={},
        policy=policy,
        trace=None,
    )


@pytest.mark.asyncio
async def test_shell_exec_returns_stdout_to_prompt_and_preview(tmp_path: Path) -> None:
    registry = ToolRegistry()
    result = await registry.execute(
        ToolExecutionRequest(tool_id="shell.exec", arguments={"command": "pwd"}),
        _context(tmp_path),
    )

    assert result.ok is True
    assert result.output["exitCode"] == 0
    assert result.output["stdout"].strip() == str(tmp_path)
    assert str(tmp_path) in result.to_prompt_payload()
    assert result.to_event_payload()["preview"]["preview"].endswith(str(tmp_path))


@pytest.mark.asyncio
async def test_shell_exec_failed_command_preserves_stdout_stderr(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    registry = ToolRegistry()
    result = await registry.execute(
        ToolExecutionRequest(tool_id="shell.exec", arguments={"command": "grep missing README.md"}),
        _context(tmp_path),
    )

    assert result.ok is False
    assert result.output["exitCode"] == 1
    assert result.output["stdout"] == ""
    assert "exit 1" in result.error
    assert '"exitCode": 1' in result.to_prompt_payload()


@pytest.mark.asyncio
async def test_shell_exec_allows_allowlisted_chain(tmp_path: Path) -> None:
    # Both pwd and git are in the default shell_allowlist — chain should succeed.
    registry = ToolRegistry()
    result = await registry.execute(
        ToolExecutionRequest(tool_id="shell.exec", arguments={"command": "pwd && pwd"}),
        _context_with_policy(tmp_path, policy_for_task_mode(None)),
    )

    assert result.ok is True
    assert result.output["policyDecision"] == "allowed"
    assert str(tmp_path) in result.output["stdout"]


@pytest.mark.asyncio
async def test_shell_exec_blocks_chain_with_non_allowlisted_command(tmp_path: Path) -> None:
    # curl is not in the default shell_allowlist — chain must be blocked.
    registry = ToolRegistry()
    result = await registry.execute(
        ToolExecutionRequest(tool_id="shell.exec", arguments={"command": "git status && curl http://example.com"}),
        _context_with_policy(tmp_path, policy_for_task_mode(None)),
    )

    assert result.ok is False
    assert result.output["policyDecision"] == "unsafe_unknown"
    assert "chain blocked" in result.error


@pytest.mark.asyncio
async def test_shell_exec_blocks_pipes_in_default_mode(tmp_path: Path) -> None:
    # Pipes are hard-blocked even when all commands are individually safe.
    registry = ToolRegistry()
    result = await registry.execute(
        ToolExecutionRequest(tool_id="shell.exec", arguments={"command": "git log | grep fix"}),
        _context_with_policy(tmp_path, policy_for_task_mode(None)),
    )

    assert result.ok is False
    assert result.output["policyDecision"] == "unsafe_unknown"


@pytest.mark.asyncio
async def test_full_access_shell_exec_allows_shell_syntax(tmp_path: Path) -> None:
    registry = ToolRegistry()
    result = await registry.execute(
        ToolExecutionRequest(tool_id="shell.exec", arguments={"command": "printf hi | tr a-z A-Z"}),
        _context_with_policy(tmp_path, policy_for_task_mode("full-access")),
    )

    assert result.ok is True
    assert result.output["exitCode"] == 0
    assert result.output["stdout"] == "HI"
    assert result.output["policySummary"] == "Full-access shell command executed with the current user's permissions."


@pytest.mark.asyncio
async def test_full_access_shell_exec_requires_approval_for_high_risk_commands(tmp_path: Path) -> None:
    registry = ToolRegistry()
    result = await registry.execute(
        ToolExecutionRequest(tool_id="shell.exec", arguments={"command": "sudo reboot"}),
        _context_with_policy(tmp_path, policy_for_task_mode("full-access")),
    )

    assert result.ok is False
    assert result.output["policyDecision"] == "approval_required"
    assert "approval required" in result.error


@pytest.mark.asyncio
async def test_guarded_find_delete_is_blocked(tmp_path: Path) -> None:
    # `find` is allowlisted, but -delete writes — guarded mode must block it.
    registry = ToolRegistry()
    result = await registry.execute(
        ToolExecutionRequest(tool_id="shell.exec", arguments={"command": "find . -delete"}),
        _context_with_policy(tmp_path, policy_for_task_mode(None)),
    )
    assert result.ok is False
    assert result.output["policyDecision"] == "write_blocked"
    assert "find predicate" in result.error


@pytest.mark.asyncio
async def test_guarded_find_exec_is_blocked(tmp_path: Path) -> None:
    registry = ToolRegistry()
    result = await registry.execute(
        ToolExecutionRequest(tool_id="shell.exec", arguments={"command": "find . -exec rm {} +"}),
        _context_with_policy(tmp_path, policy_for_task_mode(None)),
    )
    assert result.ok is False
    assert result.output["policyDecision"] == "write_blocked"


@pytest.mark.asyncio
async def test_guarded_find_readonly_still_allowed(tmp_path: Path) -> None:
    # Read-only find predicates must still pass the guard (exit 0, no matches).
    registry = ToolRegistry()
    result = await registry.execute(
        ToolExecutionRequest(tool_id="shell.exec", arguments={"command": "find . -name nonexistent.py"}),
        _context_with_policy(tmp_path, policy_for_task_mode(None)),
    )
    assert result.ok is True
    assert result.output["policyDecision"] != "write_blocked"


@pytest.mark.asyncio
async def test_guarded_git_branch_delete_is_blocked(tmp_path: Path) -> None:
    # `git branch` is read-safelisted, but -D deletes a ref.
    registry = ToolRegistry()
    result = await registry.execute(
        ToolExecutionRequest(tool_id="shell.exec", arguments={"command": "git branch -D main"}),
        _context_with_policy(tmp_path, policy_for_task_mode(None)),
    )
    assert result.ok is False
    assert result.output["policyDecision"] == "write_blocked"


@pytest.mark.asyncio
async def test_guarded_git_branch_create_is_blocked(tmp_path: Path) -> None:
    # A bare positional branch name creates a ref — also a write.
    registry = ToolRegistry()
    result = await registry.execute(
        ToolExecutionRequest(tool_id="shell.exec", arguments={"command": "git branch newbranch"}),
        _context_with_policy(tmp_path, policy_for_task_mode(None)),
    )
    assert result.ok is False
    assert result.output["policyDecision"] == "write_blocked"


@pytest.mark.asyncio
async def test_guarded_find_delete_blocked_inside_chain(tmp_path: Path) -> None:
    # The guard must also run on each chain segment, not just single commands.
    registry = ToolRegistry()
    result = await registry.execute(
        ToolExecutionRequest(tool_id="shell.exec", arguments={"command": "pwd && find . -delete"}),
        _context_with_policy(tmp_path, policy_for_task_mode(None)),
    )
    assert result.ok is False
    assert result.output["policyDecision"] == "write_blocked"


def test_clip_with_marker_flags_truncation() -> None:
    from copenet.core.tools.handlers._shared import _clip_with_marker

    assert _clip_with_marker("short", 100, "stdout") == "short"
    clipped = _clip_with_marker("x" * 50, 10, "stdout")
    assert clipped.startswith("x" * 10)
    assert "[stdout truncated at 10 chars; 50 total]" in clipped


@pytest.mark.asyncio
async def test_tool_error_is_surfaced_in_output_not_just_error(tmp_path: Path) -> None:
    # files.rg with no pattern raises ValueError; the native/Responses loops feed
    # the model only result.output, so the error must live there too (not just .error).
    registry = ToolRegistry()
    result = await registry.execute(
        ToolExecutionRequest(tool_id="files.rg", arguments={}),
        _context_with_policy(tmp_path, policy_for_task_mode(None)),
    )
    assert result.ok is False
    assert isinstance(result.output, dict)
    assert result.output.get("policyDecision") == "tool_error"
    assert "pattern" in str(result.output.get("error", "")).lower()


# --- Ask mode (Brick D): off-allowlist commands prompt instead of silently blocking ---


@pytest.mark.asyncio
async def test_ask_mode_allowlisted_command_runs_silently(tmp_path: Path) -> None:
    # An allowlisted read still runs without any prompt in Ask mode.
    registry = ToolRegistry()
    result = await registry.execute(
        ToolExecutionRequest(tool_id="shell.exec", arguments={"command": "pwd"}),
        _context_with_policy(tmp_path, policy_for_task_mode("ask")),
    )
    assert result.ok is True
    assert result.output["policyDecision"] == "allowed"
    assert result.output["stdout"].strip() == str(tmp_path)


@pytest.mark.asyncio
async def test_ask_mode_non_allowlisted_command_requests_approval(tmp_path: Path) -> None:
    # A command outside the allowlist becomes an approval prompt, not a hard block.
    registry = ToolRegistry()
    result = await registry.execute(
        ToolExecutionRequest(tool_id="shell.exec", arguments={"command": "printf hi"}),
        _context_with_policy(tmp_path, policy_for_task_mode("ask")),
    )
    assert result.ok is False
    assert result.output["policyDecision"] == "approval_required"
    # The exact command must ride along so the approval gate can re-run it.
    assert result.output["command"] == "printf hi"


@pytest.mark.asyncio
async def test_ask_mode_write_predicate_requests_approval(tmp_path: Path) -> None:
    # In read-only this is write_blocked; in Ask mode it prompts the operator.
    registry = ToolRegistry()
    result = await registry.execute(
        ToolExecutionRequest(tool_id="shell.exec", arguments={"command": "find . -delete"}),
        _context_with_policy(tmp_path, policy_for_task_mode("ask")),
    )
    assert result.ok is False
    assert result.output["policyDecision"] == "approval_required"


@pytest.mark.asyncio
async def test_ask_mode_approved_command_runs_with_full_shell(tmp_path: Path) -> None:
    # Once the operator approves a command (it lands in approved_commands), the
    # re-run executes it with full shell syntax — pipes included.
    registry = ToolRegistry()
    context = _context_with_policy(tmp_path, policy_for_task_mode("ask"))
    context.ephemeral["approved_commands"] = {"printf hi | tr a-z A-Z"}
    result = await registry.execute(
        ToolExecutionRequest(tool_id="shell.exec", arguments={"command": "printf hi | tr a-z A-Z"}),
        context,
    )
    assert result.ok is True
    assert result.output["policyDecision"] == "allowed"
    assert result.output["stdout"] == "HI"


@pytest.mark.asyncio
async def test_read_only_non_allowlisted_command_still_hard_blocks(tmp_path: Path) -> None:
    # Read-only (default) must keep its byte-for-byte behavior: a hard block.
    registry = ToolRegistry()
    result = await registry.execute(
        ToolExecutionRequest(tool_id="shell.exec", arguments={"command": "printf hi"}),
        _context_with_policy(tmp_path, policy_for_task_mode(None)),
    )
    assert result.ok is False
    assert result.output["policyDecision"] == "unsafe_unknown"


# --- Global allowlist / standing approvals (Brick E) ---


def test_permission_store_add_is_idempotent_and_normalized(tmp_path: Path) -> None:
    from copenet.core.permissions import PermissionStore

    store = PermissionStore(path=tmp_path / "permissions.json")
    store.add("npm   test")
    store.add("npm test")  # same command, different spacing
    assert [e["command"] for e in store.list_commands()] == ["npm test"]
    assert store.is_allowed("npm test") is True
    assert store.is_allowed("npm run build") is False
    assert store.remove("npm test") is True
    assert store.is_allowed("npm test") is False


def test_permission_store_persists_across_instances(tmp_path: Path) -> None:
    from copenet.core.permissions import PermissionStore

    path = tmp_path / "permissions.json"
    PermissionStore(path=path).add("printf hi")
    assert PermissionStore(path=path).is_allowed("printf hi") is True


@pytest.mark.asyncio
async def test_standing_allowlist_runs_command_in_read_only_mode(tmp_path: Path) -> None:
    # A globally-allowed command runs (with full shell) even in plain read-only mode.
    from copenet.core.permissions import PermissionStore

    registry = ToolRegistry()
    context = _context_with_policy(tmp_path, policy_for_task_mode(None))
    store = PermissionStore(path=tmp_path / "permissions.json")
    store.add("printf hi | tr a-z A-Z")
    object.__setattr__(context, "permission_store", store)
    result = await registry.execute(
        ToolExecutionRequest(tool_id="shell.exec", arguments={"command": "printf hi | tr a-z A-Z"}),
        context,
    )
    assert result.ok is True
    assert result.output["policyDecision"] == "allowed"
    assert result.output["stdout"] == "HI"


@pytest.mark.asyncio
async def test_unlisted_command_still_blocks_with_permission_store_present(tmp_path: Path) -> None:
    # The store must not relax anything for commands that aren't on it.
    from copenet.core.permissions import PermissionStore

    registry = ToolRegistry()
    context = _context_with_policy(tmp_path, policy_for_task_mode(None))
    object.__setattr__(context, "permission_store", PermissionStore(path=tmp_path / "permissions.json"))
    result = await registry.execute(
        ToolExecutionRequest(tool_id="shell.exec", arguments={"command": "printf hi"}),
        context,
    )
    assert result.ok is False
    assert result.output["policyDecision"] == "unsafe_unknown"
