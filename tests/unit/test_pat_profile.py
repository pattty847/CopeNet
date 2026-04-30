from __future__ import annotations

import json
from pathlib import Path

from copenet.core.runtime import RunRecord, RunStore


def _write_template(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "identity.json").write_text(
        json.dumps(
            {
                "profileId": "pat-profile:template",
                "displayName": "Operator",
                "configured": False,
                "priorities": [],
                "goals": [],
                "tonePreference": {
                    "directness": "balanced",
                    "formality": "casual",
                    "preferBullets": True,
                },
                "noiseFilters": [],
                "scheduleBasics": [],
                "recurringConstraints": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (root / "observed_tendencies.json").write_text("[]\n", encoding="utf-8")
    (root / "guidance_rules.json").write_text("[]\n", encoding="utf-8")
    (root / "notes.md").write_text("# Notes\n\nTemplate notes.\n", encoding="utf-8")


def _make_run(*, session_key: str, user_message: str) -> RunRecord:
    return RunRecord(
        run_id=f"run-{abs(hash((session_key, user_message)))}",
        session_key=session_key,
        provider="fake",
        model="model-a",
        status="ok",
        user_message=user_message,
        tool_execution_mode="none",
        will_attempt_tool_loop=False,
        output_summary="ok",
    )


def test_pat_profile_template_only_load_returns_inactive_bundle(tmp_path: Path) -> None:
    from copenet.core.profile import PatProfileService

    template_dir = tmp_path / "template"
    overlay_dir = tmp_path / "overlay"
    _write_template(template_dir)

    service = PatProfileService(template_dir=template_dir, overlay_dir=overlay_dir, run_store=RunStore(tmp_path / "runs"))
    bundle = service.load_bundle()

    assert bundle.profile is None
    assert bundle.overlay_present is False
    assert bundle.identity["displayName"] == "Operator"
    assert bundle.notes_markdown.startswith("# Notes")
    assert bundle.observed_tendencies == []
    assert bundle.guidance_rules == []
    assert bundle.changelog == []


def test_pat_profile_local_overlay_overrides_template_and_keeps_layers_distinct(tmp_path: Path) -> None:
    from copenet.core.profile import PatProfileService

    template_dir = tmp_path / "template"
    overlay_dir = tmp_path / "overlay"
    _write_template(template_dir)
    overlay_dir.mkdir(parents=True, exist_ok=True)
    (overlay_dir / "identity.json").write_text(
        json.dumps(
            {
                "profileId": "pat-profile:patrick",
                "displayName": "Patrick Cope",
                "configured": True,
                "priorities": [{"id": "school", "label": "School", "weight": 1.0}],
                "goals": [{"id": "ship", "text": "Ship CopeNet", "source": "explicit", "updatedAt": "2026-04-30T00:00:00Z"}],
                "tonePreference": {
                    "directness": "terse",
                    "formality": "casual",
                    "preferBullets": False,
                },
                "noiseFilters": ["ignore china crypto bans unless price moves materially"],
                "scheduleBasics": ["Starbucks shifts vary weekly"],
                "recurringConstraints": ["School work due tonight outranks market noise"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (overlay_dir / "observed_tendencies.json").write_text(
        json.dumps(
            [
                {
                    "id": "obs-crypto-first",
                    "label": "Often checks crypto before school tasks",
                    "confidence": 0.93,
                    "evidenceCount": 4,
                    "source": "session_observation",
                    "updatedAt": "2026-04-30T00:00:00Z",
                }
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    (overlay_dir / "guidance_rules.json").write_text(
        json.dumps(
            [
                {
                    "id": "guide-school-first",
                    "rule": "When homework is due tonight, push school before crypto.",
                    "priority": "high",
                    "source": "explicit",
                    "rationale": "Pat explicitly asked for corrective nudges.",
                    "updatedAt": "2026-04-30T00:00:00Z",
                }
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    (overlay_dir / "notes.md").write_text("# Pat Notes\n\nReal local overlay.\n", encoding="utf-8")

    service = PatProfileService(template_dir=template_dir, overlay_dir=overlay_dir, run_store=RunStore(tmp_path / "runs"))
    bundle = service.load_bundle()

    assert bundle.profile is not None
    assert bundle.overlay_present is True
    assert bundle.profile.display_name == "Patrick Cope"
    assert bundle.profile.tone_preference["directness"] == "terse"
    assert bundle.observed_tendencies[0].label.startswith("Often checks crypto")
    assert bundle.guidance_rules[0].rule.startswith("When homework is due tonight")
    assert bundle.notes_markdown.startswith("# Pat Notes")


def test_pat_profile_apply_post_run_updates_accepts_explicit_statements_and_appends_changelog(tmp_path: Path) -> None:
    from copenet.core.profile import PatProfileService

    template_dir = tmp_path / "template"
    overlay_dir = tmp_path / "overlay"
    _write_template(template_dir)

    service = PatProfileService(template_dir=template_dir, overlay_dir=overlay_dir, run_store=RunStore(tmp_path / "runs"))
    changes = service.apply_post_run_updates(
        user_message="Please lead with the punchline and ignore China crypto ban headlines unless price moves materially.",
        run_record=_make_run(session_key="alpha", user_message="Please lead with the punchline and ignore China crypto ban headlines unless price moves materially."),
    )

    bundle = service.load_bundle()
    assert changes
    assert bundle.profile is not None
    assert bundle.profile.tone_preference["directness"] == "terse"
    assert any("china crypto ban" in item.lower() for item in bundle.profile.noise_filters)
    assert bundle.changelog


def test_pat_profile_repeated_patterns_can_create_observed_tendency(tmp_path: Path) -> None:
    from copenet.core.profile import PatProfileService

    template_dir = tmp_path / "template"
    overlay_dir = tmp_path / "overlay"
    run_store = RunStore(tmp_path / "runs")
    _write_template(template_dir)
    service = PatProfileService(template_dir=template_dir, overlay_dir=overlay_dir, run_store=run_store)

    prior = [
        _make_run(session_key="alpha", user_message="Check crypto and BTC price action."),
        _make_run(session_key="beta", user_message="Need the crypto chart before anything else."),
        _make_run(session_key="gamma", user_message="Let's check crypto first, then maybe school."),
    ]
    for record in prior:
        run_store.create(record)

    changes = service.apply_post_run_updates(
        user_message="Crypto first again, then maybe school later.",
        run_record=_make_run(session_key="delta", user_message="Crypto first again, then maybe school later."),
    )

    bundle = service.load_bundle()
    assert changes
    assert any("crypto" in tendency.label.lower() for tendency in bundle.observed_tendencies)


def test_pat_profile_rejects_weak_single_pass_inference(tmp_path: Path) -> None:
    from copenet.core.profile import PatProfileService

    template_dir = tmp_path / "template"
    overlay_dir = tmp_path / "overlay"
    _write_template(template_dir)

    service = PatProfileService(template_dir=template_dir, overlay_dir=overlay_dir, run_store=RunStore(tmp_path / "runs"))
    changes = service.apply_post_run_updates(
        user_message="I checked crypto once today.",
        run_record=_make_run(session_key="alpha", user_message="I checked crypto once today."),
    )

    bundle = service.load_bundle()
    assert changes == []
    assert bundle.observed_tendencies == []


def test_pat_profile_builds_return_briefing_from_recent_runs_and_profile_changes(tmp_path: Path) -> None:
    from copenet.core.profile import PatProfileService

    template_dir = tmp_path / "template"
    overlay_dir = tmp_path / "overlay"
    run_store = RunStore(tmp_path / "runs")
    _write_template(template_dir)
    service = PatProfileService(template_dir=template_dir, overlay_dir=overlay_dir, run_store=run_store)

    record = _make_run(session_key="alpha", user_message="Please lead with the punchline.")
    record.output_summary = "Summarized the provider adapter files."
    record.tool_steps = [{"toolId": "files.read", "ok": True, "summary": "Read README"}]
    run_store.create(record)
    service.apply_post_run_updates(
        user_message="Please lead with the punchline.",
        run_record=record,
    )

    briefing = service.build_return_briefing()

    assert briefing is not None
    assert briefing.activity_items
    assert any("Summarized the provider adapter files" in item.summary for item in briefing.activity_items)
    assert briefing.notice_text
