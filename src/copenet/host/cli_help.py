"""Self-describing `copenet help` guide.

A single friendly cheat sheet for the things you do often but forget the exact
incantation for: run the host, expose it on the tailnet, fire one-shot test prompts
through the real orchestrator, manage provider auth, turn on tracing.

The "All commands" section walks the live argparse parser, so new subcommands show
up here automatically without anyone hand-maintaining a second list.
"""

from __future__ import annotations

import argparse


# Curated workflows — the high-value recipes worth memorializing. Each entry is
# (one-line intent, example command). Keep these task-shaped, not exhaustive; the
# auto-generated command list below covers the full surface.
_RECIPES: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "Run the host + UI",
        [
            ("copenet", "serve on 127.0.0.1:17123 — open http://localhost:17123"),
            ("COPNET_PORT=17124 copenet", "use a custom port"),
            ("COPNET_WORKDIR=/path/to/repo copenet", "set the workspace root for full-access tools"),
            ("COPNET_TRACE=1 copenet", "write per-run JSONL traces to ~/.copenet/logs/runs/"),
        ],
    ),
    (
        "Reach it from your phone (tailnet)",
        [
            ("COPNET_HOST=tailscale copenet", "serve privately on your tailnet IP (NOT local wifi)"),
            ("tailscale serve --bg --https=443 17123", "add HTTPS — needed for the mic from other devices"),
        ],
    ),
    (
        "Fire one-shot test prompts through the real orchestrator",
        [
            (
                'copenet chat send --session 69696469 "Run pwd, then tell me stdout."',
                "create/continue a session; streams assistant text + tool calls",
            ),
            (
                'copenet chat send --provider openai-codex --model gpt-5.5 "..."',
                "pin a provider/model for the turn",
            ),
            (
                'copenet chat send --task-mode full-access "edit src/foo.py ..."',
                "allow write + unrestricted shell tools for the turn",
            ),
            ("copenet chat send --json \"...\"", "capture raw events as JSON instead of a transcript"),
            ("copenet chat history --session 69696469 --limit 12", "print recent turns from a session"),
        ],
    ),
    (
        "Provider auth (openai-codex OAuth)",
        [
            ("copenet auth login", "browser OAuth login"),
            ("copenet auth login --no-browser", "print the authorize URL instead of opening a browser"),
            ("copenet auth status", "show current auth state"),
            ("copenet auth logout", "clear stored auth"),
        ],
    ),
]


# Environment variables worth remembering, with their default.
_ENV_VARS: list[tuple[str, str]] = [
    ("COPNET_HOST", "bind host: 127.0.0.1 (default) | tailscale | 0.0.0.0 | explicit IP"),
    ("COPNET_PORT", "bind port (default 17123)"),
    ("COPNET_WORKDIR", "workspace root for tools (default: current directory)"),
    ("COPNET_TOKEN", "gateway auth token (default: dev-token)"),
    ("COPNET_TRACE", "set to 1 to write per-run JSONL traces"),
    ("NASA_API_KEY", "key for the NASA Picture of the Day feature (loaded from .env)"),
]


def _format_recipes() -> list[str]:
    lines: list[str] = []
    for title, examples in _RECIPES:
        lines.append(f"\n{title}:")
        width = max((len(cmd) for cmd, _ in examples), default=0)
        for cmd, note in examples:
            lines.append(f"  {cmd.ljust(width)}   {note}")
    return lines


def _format_env_vars() -> list[str]:
    lines = ["\nEnvironment variables:"]
    width = max((len(name) for name, _ in _ENV_VARS), default=0)
    for name, note in _ENV_VARS:
        lines.append(f"  {name.ljust(width)}   {note}")
    return lines


def _format_all_commands(parser: argparse.ArgumentParser) -> list[str]:
    """Walk the parser's subcommands so this list never drifts from reality."""
    lines = ["\nAll commands (auto-listed from the CLI):"]
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        for name, subparser in action.choices.items():
            help_text = _subparser_help(action, name)
            lines.append(f"  copenet {name.ljust(8)} {help_text}")
            lines.extend(_format_nested_commands(subparser, name))
    return lines


def _format_nested_commands(subparser: argparse.ArgumentParser, parent: str) -> list[str]:
    lines: list[str] = []
    for action in subparser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        for name, _ in action.choices.items():
            help_text = _subparser_help(action, name)
            lines.append(f"    copenet {parent} {name.ljust(8)} {help_text}")
    return lines


def _subparser_help(action: argparse._SubParsersAction, name: str) -> str:
    for choice_action in action._choices_actions:
        if choice_action.dest == name:
            return choice_action.help or ""
    return ""


def render_guide(parser: argparse.ArgumentParser) -> str:
    """Build the full self-describing guide string."""
    header = [
        "CopeNet — local agent gateway",
        "Harness-first, continuity-first, identity-aware. Run it, talk to it, extend it.",
    ]
    sections = [
        "\n".join(header),
        *_format_recipes(),
        *_format_env_vars(),
        *_format_all_commands(parser),
        "\nMore detail:  copenet --help  |  copenet chat send --help  |  copenet auth --help",
    ]
    return "\n".join(sections) + "\n"
