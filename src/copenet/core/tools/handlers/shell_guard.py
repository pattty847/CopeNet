"""Guarded shell command classification shared by single commands and chains."""

from __future__ import annotations

from copenet.core.tools.contracts import ToolBlockedError, ToolExecutionContext

from ._shared import display_path, policy_decision_for_scope, resolve_relative_path, scope_for_path

_SAFE_GIT_SUBCOMMANDS = {
    "status",
    "diff",
    "show",
    "log",
    "rev-parse",
    "branch",
    "ls-files",
    "grep",
}
_WRITE_LIKE_GIT_SUBCOMMANDS = {
    "add",
    "apply",
    "checkout",
    "cherry-pick",
    "clean",
    "commit",
    "merge",
    "mv",
    "pull",
    "push",
    "rebase",
    "reset",
    "restore",
    "revert",
    "rm",
    "stash",
    "switch",
    "tag",
}

# Action predicates that make `find` write or execute. `find` is allowlisted as a
# read tool, but the allowlist only inspects argv[0] — so `find . -delete` and
# `find . -exec rm {} +` would pass straight through. Block them in guarded mode.
_FIND_WRITE_PREDICATES = frozenset({
    "-delete",
    "-exec",
    "-execdir",
    "-ok",
    "-okdir",
    "-fprint",
    "-fprintf",
    "-fprint0",
    "-fls",
})

# `git branch` is on the read safelist (listing branches is read-only), but these
# flags — or any positional branch-name argument — create, delete, rename, move,
# or re-point refs. Block those forms in guarded mode; plain listing still passes.
_GIT_BRANCH_WRITE_FLAGS = frozenset({
    "-d",
    "-D",
    "--delete",
    "-m",
    "-M",
    "--move",
    "-c",
    "-C",
    "--copy",
    "-f",
    "--force",
    "-u",
    "--set-upstream-to",
    "--unset-upstream",
    "--edit-description",
})


def _blocked_write_option(argv: list[str]) -> str | None:
    cmd = argv[0]
    for token in argv[1:]:
        option = token.split("=", 1)[0]
        if cmd == "git" and len(argv) > 1 and argv[1] in {"diff", "log", "show"} and option == "--output":
            return token
        if cmd == "tree" and (option == "--output" or token.startswith("-o")):
            return token
        if cmd == "rg" and option in {"--pre", "--pre-glob"}:
            return token
    return None


def _assert_no_write_predicates(argv: list[str], command: str, context: ToolExecutionContext) -> None:
    """Block write/exec forms of otherwise-allowlisted commands in guarded mode.

    The shell allowlist only checks argv[0], so write-capable flags on read
    binaries slip through. This is the second gate (after the allowlist) that
    keeps guarded mode actually read-only. Full-access uses the unrestricted
    shell path in shell.py.
    """
    cmd = argv[0]
    write_option = _blocked_write_option(argv)
    if write_option is not None:
        raise ToolBlockedError(
            f"{cmd} option '{write_option}' can write or execute and is blocked in guarded mode",
            target=command,
            workspace_root=str(context.session_workspace_root),
            access_action="write",
            policy_decision="write_blocked",
            policy_summary="Write and exec options require full-access.",
        )
    if cmd == "find":
        for token in argv[1:]:
            base = token.split("=", 1)[0]
            if base in _FIND_WRITE_PREDICATES:
                raise ToolBlockedError(
                    f"find predicate '{base}' can write or execute and is blocked in guarded mode",
                    target=command,
                    workspace_root=str(context.session_workspace_root),
                    access_action="write",
                    policy_decision="write_blocked",
                    policy_summary="find write/exec predicates require full-access.",
                )
    elif cmd == "git" and len(argv) > 1 and argv[1] == "branch":
        for token in argv[2:]:
            base = token.split("=", 1)[0]
            if base in _GIT_BRANCH_WRITE_FLAGS or not token.startswith("-"):
                raise ToolBlockedError(
                    "git branch with a write flag or branch-name argument is blocked in guarded mode",
                    target=command,
                    workspace_root=str(context.session_workspace_root),
                    access_action="write",
                    policy_decision="write_blocked",
                    policy_summary="Only read-only `git branch` listing is allowed outside full-access.",
                )


def _path_candidate(token: str) -> bool:
    if not token or token.startswith("-"):
        return False
    if token in {".", ".."}:
        return True
    return "/" in token or token.startswith("~")


def _shell_access_metadata(argv: list[str], context: ToolExecutionContext) -> dict[str, str | None]:
    command = " ".join(argv)
    default = {
        "target": command,
        "workspaceRoot": str(context.session_workspace_root),
        "scope": None,
        "accessAction": "read",
        "policyDecision": "allowed",
        "policySummary": "Shell command stayed within the home workspace.",
    }
    cmd = argv[0]

    if cmd == "pwd":
        default["target"] = display_path(context.workdir, context)
        default["scope"] = "inside_workspace"
        return default

    if cmd == "git":
        subcommand = argv[1] if len(argv) > 1 else "status"
        if subcommand in _WRITE_LIKE_GIT_SUBCOMMANDS:
            raise ToolBlockedError(
                f"git {subcommand} may write to the repository and is blocked in shell.exec v1",
                target=command,
                workspace_root=str(context.session_workspace_root),
                access_action="write",
                policy_decision="write_blocked",
                policy_summary="Shell write blocked outside dedicated patch/apply flows.",
            )
        if subcommand not in _SAFE_GIT_SUBCOMMANDS:
            raise ToolBlockedError(
                f"git {subcommand} is not classified as safely read-only for shell.exec v1",
                target=command,
                workspace_root=str(context.session_workspace_root),
                access_action="unknown",
                policy_decision="unsafe_unknown",
                policy_summary="Shell effect is not confidently read-only.",
            )
        default["target"] = display_path(context.workdir, context)
        default["scope"] = "inside_workspace"
        return default

    path_tokens = [token for token in argv[1:] if _path_candidate(token)]
    if not path_tokens:
        default["target"] = command
        default["scope"] = "inside_workspace"
        return default

    resolved = resolve_relative_path(path_tokens[-1], context)
    scope = scope_for_path(resolved, context)
    default["target"] = display_path(resolved, context)
    default["scope"] = scope
    default["policyDecision"] = policy_decision_for_scope(scope)
    default["policySummary"] = (
        "Shell read roamed outside the home workspace."
        if scope == "outside_workspace"
        else "Shell command stayed within the home workspace."
    )
    return default


def classify_guarded_command(argv: list[str], command: str, context: ToolExecutionContext) -> dict[str, str | None]:
    """Validate one command before execution and return its access metadata."""
    if argv[0] not in context.policy.shell_allowlist:
        raise ToolBlockedError(
            f"command not allowed: {argv[0]}",
            target=command,
            workspace_root=str(context.session_workspace_root),
            access_action="unknown",
            policy_decision="unsafe_unknown",
            policy_summary="Command is outside the shell allowlist.",
        )
    _assert_no_write_predicates(argv, command, context)
    return _shell_access_metadata(argv, context)
