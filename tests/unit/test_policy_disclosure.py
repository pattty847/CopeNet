"""The model must be told the Access level it is running under.

A read-only run used to be told nothing at all — the `none` overlay was "No
additional task overlay" and shell.exec's description named no allowlist — so the
model discovered `echo` was blocked by spending a tool call on it.
"""

from __future__ import annotations

from copenet.core.tools import disclose_policy_in_descriptions, policy_for_task_mode
from copenet.core.tools.contracts import ToolDescriptor
from copenet.core.tools.policy_disclosure import shell_policy_disclosure


SHELL = ToolDescriptor(id="shell.exec", name="Shell Exec", description="Run a shell command.", category="shell-read")
WRITE = ToolDescriptor(id="files.write", name="Write", description="Write a file.", category="repo-write")
READ = ToolDescriptor(id="files.read", name="Read", description="Read a file.", category="repo-read")


def test_read_only_names_every_allowed_command() -> None:
    policy = policy_for_task_mode(None)
    disclosure = shell_policy_disclosure(policy)

    assert "ACCESS: read-only" in disclosure
    for command in policy.shell_allowlist:
        assert command in disclosure
    # `echo` is the command that actually got blocked in a live probe.
    assert "echo" not in disclosure
    assert "no pipes, chaining, redirects, or globs" in disclosure


def test_ask_mode_says_the_block_is_a_pause_not_a_wall() -> None:
    disclosure = shell_policy_disclosure(policy_for_task_mode("ask"))

    assert "ACCESS: ask" in disclosure
    assert "approval_required" in disclosure
    assert "rg" in disclosure


def test_full_access_does_not_enumerate_an_allowlist_it_does_not_use() -> None:
    disclosure = shell_policy_disclosure(policy_for_task_mode("full-access", provider="openai-codex"))

    assert "ACCESS: full-access" in disclosure
    assert "approval_required" in disclosure
    assert "read-only" not in disclosure


def test_disclosure_is_appended_only_to_the_tools_it_constrains() -> None:
    policy = policy_for_task_mode(None)
    disclosed = disclose_policy_in_descriptions([SHELL, WRITE, READ], policy)
    by_id = {tool.id: tool for tool in disclosed}

    assert by_id["shell.exec"].description.startswith("Run a shell command.")
    assert "ACCESS: read-only" in by_id["shell.exec"].description
    assert "NOT available" in by_id["files.write"].description
    assert by_id["files.read"].description == "Read a file."


def test_disclosure_never_mutates_the_shared_registry_descriptors() -> None:
    """Policy differs per run; the module-level descriptors are shared."""
    original = SHELL.description
    disclose_policy_in_descriptions([SHELL], policy_for_task_mode(None))
    disclose_policy_in_descriptions([SHELL], policy_for_task_mode("full-access", provider="openai-codex"))

    assert SHELL.description == original


def test_write_disclosure_flips_with_full_access() -> None:
    guarded = disclose_policy_in_descriptions([WRITE], policy_for_task_mode(None))[0]
    full = disclose_policy_in_descriptions(
        [WRITE], policy_for_task_mode("full-access", provider="openai-codex")
    )[0]

    assert "NOT available" in guarded.description
    assert "are available" in full.description
