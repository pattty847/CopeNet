"""Tell the model the Access level it is actually running under.

Before this, a model in the default read-only mode was told nothing: the `none`
task-mode overlay is literally "No additional task overlay", and `shell.exec`'s
static description said "one read-only allowlisted command" without ever naming
the allowlist. So the model had no way to know that `echo` is not on it — it
found out by being blocked, having spent a tool call to learn a fact the harness
knew before the turn started.

The disclosure is generated from the live `ToolPolicy` rather than written into
the preset markdown, because a hand-maintained copy of `shell_allowlist` in a
prompt file drifts silently the first time someone edits the tuple.
"""

from __future__ import annotations

from dataclasses import replace

from .contracts import ToolDescriptor
from .policy import ToolPolicy


def shell_policy_disclosure(policy: ToolPolicy) -> str:
    """Return the sentence(s) describing what this policy actually permits."""
    if policy.unrestricted_shell:
        return (
            "ACCESS: full-access. Arbitrary user-level shell syntax is permitted — pipes, "
            "chaining, redirects, and scripts. High-risk commands still return "
            'policyDecision: "approval_required" instead of executing; that is a stop point '
            "to explain and propose, not a failure to work around."
        )

    allowed = ", ".join(policy.shell_allowlist)
    if policy.prompt_on_block:
        return (
            "ACCESS: ask. These commands run immediately: "
            f"{allowed}. Anything else — including other binaries, pipes, chaining, "
            'redirects, and write-capable flags — returns policyDecision: "approval_required" '
            "and pauses for the operator. Issuing such a command is the intended flow; say "
            "briefly why you need it."
        )
    return (
        "ACCESS: read-only. Only these commands run, one per call, with no shell syntax "
        f"(no pipes, chaining, redirects, or globs): {allowed}. Anything else is blocked "
        "outright — do not spend a call discovering that. Write-capable flags on these "
        "binaries (for example `find -delete`) are blocked too. If a task needs more, say so "
        "and let the operator switch Access rather than retrying."
    )


def write_policy_disclosure(policy: ToolPolicy) -> str:
    """Return the sentence describing repository write availability."""
    if "repo-write" in policy.allowed_categories:
        return "ACCESS: repository write tools are available in this session."
    return (
        "ACCESS: repository write tools are NOT available in this session. Do not plan edits "
        "you cannot make — describe the change and let the operator switch to Full Access."
    )


def disclose_policy_in_descriptions(
    tools: list[ToolDescriptor],
    policy: ToolPolicy,
) -> list[ToolDescriptor]:
    """Append the live policy to the descriptions of the tools it constrains.

    Returns new descriptors; the registry's shared module-level ones are never
    mutated, because policy differs per run.
    """
    disclosed: list[ToolDescriptor] = []
    for tool in tools:
        if tool.id == "shell.exec":
            disclosed.append(
                replace(tool, description=f"{tool.description} {shell_policy_disclosure(policy)}")
            )
            continue
        if tool.category == "repo-write":
            disclosed.append(
                replace(tool, description=f"{tool.description} {write_policy_disclosure(policy)}")
            )
            continue
        disclosed.append(tool)
    return disclosed
