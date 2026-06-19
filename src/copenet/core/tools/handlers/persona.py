"""Persona authoring tool — lets the model build a persona on request.

When the operator says "make me a sarcastic cybersecurity-mentor personality," the
model calls ``persona.author`` to create the persona and write its identity files.
The tool description IS the schematic: it tells the model what files a persona has
and what each one is for, so the model can assemble a coherent personality in one
call. Operator-data write (category "context"), same low-risk lane as memory.write.
"""

from __future__ import annotations

from ..contracts import (
    ToolBlockedError,
    ToolDescriptor,
    ToolExecutionContext,
    ToolExecutionRequest,
    ToolExecutionResult,
)

_SECTION_KEYS = ("soul", "identity", "agents", "user", "tools", "public_memory")

DESCRIPTORS = [
    ToolDescriptor(
        id="persona.author",
        name="Author Persona",
        description=(
            "Create or update a CopeNet persona — a named, file-backed personality the operator "
            "can switch to. Use this when the operator asks you to build, design, or set up a "
            "personality/persona. A persona is a folder of markdown files; provide the ones you "
            "want to fill:\n"
            "- soul: the behavioral essence — voice, temperament, how it talks and decides.\n"
            "- identity: who it is — name, role, expertise, point of view.\n"
            "- agents: operating notes — how it should use tools, memory, and handle privacy.\n"
            "- user: private operator context this persona should keep in mind.\n"
            "- tools: machine/environment notes relevant to this persona.\n"
            "- public_memory: public-safe collaboration notes it starts knowing.\n"
            "Pick a short, descriptive personaId (e.g. 'osint-recon', 'sarcastic-mentor') for a NEW "
            "persona; reusing an existing id overwrites the sections you provide. Write the sections "
            "as clear, concise markdown. This does NOT switch the active persona — the operator picks "
            "it from the Persona Home picker."
        ),
        category="context",
        input_schema={
            "type": "object",
            "properties": {
                "personaId": {"type": "string", "description": "Short kebab-case id for the persona."},
                "displayName": {"type": "string", "description": "Human-friendly name."},
                "soul": {"type": "string"},
                "identity": {"type": "string"},
                "agents": {"type": "string"},
                "user": {"type": "string"},
                "tools": {"type": "string"},
                "public_memory": {"type": "string"},
            },
            "required": ["personaId"],
            "additionalProperties": False,
        },
        safety_level="guarded",
        capabilities=["identity", "persona", "continuity"],
        evidence_role="context",
        side_effect="write",
    ),
]


async def handle_persona_author(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    service = context.persona_service
    if service is None:
        raise ToolBlockedError(
            "persona service unavailable",
            access_action="write",
            policy_summary="Persona Home is not configured for this session.",
        )
    persona_id = str(request.arguments.get("personaId") or "").strip()
    if not persona_id:
        raise ToolBlockedError(
            "persona.author requires a personaId",
            access_action="write",
            policy_summary="A persona needs a short id.",
        )
    display_name = str(request.arguments.get("displayName") or "").strip() or None
    sections = {key: str(request.arguments.get(key) or "") for key in _SECTION_KEYS}
    record = service.author_persona(persona_id=persona_id, display_name=display_name, sections=sections)
    written = record.get("writtenFiles") or []
    return ToolExecutionResult(
        tool_id="persona.author",
        ok=True,
        summary=f"Authored persona '{record['displayName']}' ({len(written)} file{'s' if len(written) != 1 else ''} written).",
        output={
            "persona": record,
            "scope": "persona",
            "accessAction": "write",
            "policyDecision": "allowed",
            "policySummary": "Persona files are user-visible identity content, editable in Persona Home.",
        },
    )


HANDLERS = {
    "persona.author": handle_persona_author,
}
