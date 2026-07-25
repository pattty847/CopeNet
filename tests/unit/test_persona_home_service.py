from __future__ import annotations

import json
from pathlib import Path

from copenet.core.persona import PersonaHomeService, PersonaPrivacyTier


def test_persona_service_scaffolds_default_home_and_loads_private_context(tmp_path: Path) -> None:
    service = PersonaHomeService(root_dir=tmp_path / "personas")

    context = service.build_prompt_context(
        provider="codex-cli",
        model="gpt-5.4",
        privacy_tier="private",
        query="help me work on CopeNet",
    )

    assert context.persona_id == "default"
    assert context.privacy_tier == "private"
    assert "CopeNet Home" in context.prompt
    assert (tmp_path / "personas" / "default" / "core" / "SOUL.md").exists()
    assert (tmp_path / "personas" / "settings.json").exists()


def test_persona_service_can_exclude_agent_operating_notes(tmp_path: Path) -> None:
    service = PersonaHomeService(root_dir=tmp_path / "personas")

    general_context = service.build_prompt_context(
        provider="openai-codex",
        model="gpt-5.5",
        privacy_tier="private",
        query="Talk with me",
        include_agent_instructions=False,
    )
    code_context = service.build_prompt_context(
        provider="openai-codex",
        model="gpt-5.5",
        privacy_tier="private",
        query="Fix the code",
        include_agent_instructions=True,
    )

    assert "CopeNet Persona Operating Notes" not in general_context.prompt
    assert not any(path.endswith("/AGENTS.md") for path in general_context.loaded_files)
    assert "CopeNet Persona Operating Notes" in code_context.prompt
    assert any(path.endswith("/AGENTS.md") for path in code_context.loaded_files)


def test_persona_service_layers_model_flavor_after_shared_core(tmp_path: Path) -> None:
    root = tmp_path / "personas"
    flavor_dir = root / "default" / "models" / "codex-cli" / "gpt-5.4"
    flavor_dir.mkdir(parents=True)
    (flavor_dir / "IDENTITY.md").write_text("# Model Flavor\n\nA crisp local engineer.\n", encoding="utf-8")
    (root / "settings.json").parent.mkdir(parents=True, exist_ok=True)
    (root / "settings.json").write_text(
        json.dumps(
            {
                "defaultPersonaId": "default",
                "defaultPrivacyTier": "private",
                "modelOverrides": {
                    "codex-cli:gpt-5.4": {
                        "personaId": "default",
                        "flavorId": "codex-cli/gpt-5.4",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    context = PersonaHomeService(root_dir=root).build_prompt_context(
        provider="codex-cli",
        model="gpt-5.4",
        privacy_tier="private",
        query="ship this feature",
    )

    assert context.flavor_id == "codex-cli/gpt-5.4"
    assert "CopeNet Home" in context.prompt
    assert "A crisp local engineer." in context.prompt
    assert context.prompt.index("CopeNet Home") < context.prompt.index("A crisp local engineer.")


def test_persona_service_filters_private_memory_from_safe_context(tmp_path: Path) -> None:
    root = tmp_path / "personas"
    memory_dir = root / "default" / "memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "MEMORY.md").write_text("Pat-private strategic details.\n", encoding="utf-8")
    (memory_dir / "PUBLIC.md").write_text("Public-safe CopeNet collaboration notes.\n", encoding="utf-8")

    service = PersonaHomeService(root_dir=root)
    private_context = service.build_prompt_context(provider="lm-studio", model="local", privacy_tier="private", query="context")
    safe_context = service.build_prompt_context(provider="lm-studio", model="local", privacy_tier="safe", query="context")
    off_context = service.build_prompt_context(provider="lm-studio", model="local", privacy_tier="off", query="context")

    assert "Pat-private strategic details." in private_context.prompt
    assert "Public-safe CopeNet collaboration notes." in safe_context.prompt
    assert "Pat-private strategic details." not in safe_context.prompt
    assert off_context.prompt == ""


def test_persona_settings_update_persists_defaults_and_overrides(tmp_path: Path) -> None:
    service = PersonaHomeService(root_dir=tmp_path / "personas")

    settings = service.update_settings(
        default_persona_id="default",
        default_privacy_tier="safe",
        model_overrides={
            "claude-cli:sonnet": {
                "personaId": "default",
                "flavorId": "claude-cli/sonnet",
            }
        },
    )

    reloaded = PersonaHomeService(root_dir=tmp_path / "personas").load_settings()
    assert settings.default_privacy_tier == "safe"
    assert reloaded.default_privacy_tier == "safe"
    assert reloaded.model_overrides["claude-cli:sonnet"].flavor_id == "claude-cli/sonnet"


def test_persona_flavor_draft_can_be_saved_after_approval(tmp_path: Path) -> None:
    service = PersonaHomeService(root_dir=tmp_path / "personas")
    draft = {
        "displayName": "Codex Forge",
        "identityMarkdown": "# Codex Forge\n\nA steady builder.\n",
        "soulMarkdown": "# Codex Forge Soul\n\nPractical and warm.\n",
        "notesMarkdown": "Keeps shared memory separate from flavor.\n",
    }

    flavor = service.save_flavor(
        provider="codex-cli",
        model="gpt-5.4",
        draft=draft,
    )

    assert flavor.flavor_id == "codex-cli/gpt-5.4"
    assert (tmp_path / "personas" / "default" / "models" / "codex-cli" / "gpt-5.4" / "IDENTITY.md").read_text(encoding="utf-8").startswith("# Codex Forge")
    assert service.build_prompt_context(provider="codex-cli", model="gpt-5.4", privacy_tier="private", query="").flavor_id == "codex-cli/gpt-5.4"
