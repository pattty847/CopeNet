"""File-backed Pat Profile loading, maintenance, and briefing support."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from copenet._paths import default_pat_profile_dir
from copenet.core.runtime import RunRecord, RunStore
from copenet.core.sessions.session_store import utc_now_iso


def _profile_template_dir() -> Path:
    return Path(__file__).resolve().parent / "templates"


def _read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_markdown(path: Path, fallback: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return fallback


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict(dict(merged[key]), value)
        else:
            merged[key] = value
    return merged


def _as_str(value: Any) -> str:
    return str(value or "").strip()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = _as_str(item)
        if text:
            out.append(text)
    return out


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _timestamp_from_record(record: RunRecord) -> str:
    return record.completed_at or record.started_at or utc_now_iso()


@dataclass(frozen=True)
class PatProfile:
    profile_id: str
    display_name: str
    active: bool
    source: str
    priorities: list[dict[str, Any]]
    goals: list[dict[str, Any]]
    tone_preference: dict[str, Any]
    noise_filters: list[str]
    last_updated_at: str
    changelog_count: int

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "profileId": self.profile_id,
            "displayName": self.display_name,
            "active": self.active,
            "source": self.source,
            "priorities": [dict(item) for item in self.priorities],
            "goals": [dict(item) for item in self.goals],
            "tonePreference": dict(self.tone_preference),
            "noiseFilters": list(self.noise_filters),
            "lastUpdatedAt": self.last_updated_at,
            "changelogCount": self.changelog_count,
        }


@dataclass(frozen=True)
class ObservedTendency:
    id: str
    label: str
    confidence: float
    evidence_count: int
    source: str
    updated_at: str

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "ObservedTendency":
        return cls(
            id=_as_str(raw.get("id")) or str(uuid4()),
            label=_as_str(raw.get("label")),
            confidence=float(raw.get("confidence") or 0.0),
            evidence_count=int(raw.get("evidenceCount") or raw.get("evidence_count") or 0),
            source=_as_str(raw.get("source")) or "session_observation",
            updated_at=_as_str(raw.get("updatedAt") or raw.get("updated_at")) or utc_now_iso(),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "confidence": self.confidence,
            "evidenceCount": self.evidence_count,
            "source": self.source,
            "updatedAt": self.updated_at,
        }


@dataclass(frozen=True)
class GuidanceRule:
    id: str
    rule: str
    priority: str
    source: str
    rationale: str | None
    updated_at: str

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "GuidanceRule":
        return cls(
            id=_as_str(raw.get("id")) or str(uuid4()),
            rule=_as_str(raw.get("rule")),
            priority=_as_str(raw.get("priority")) or "medium",
            source=_as_str(raw.get("source")) or "explicit",
            rationale=_as_str(raw.get("rationale")) or None,
            updated_at=_as_str(raw.get("updatedAt") or raw.get("updated_at")) or utc_now_iso(),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "rule": self.rule,
            "priority": self.priority,
            "source": self.source,
            "rationale": self.rationale,
            "updatedAt": self.updated_at,
        }


@dataclass(frozen=True)
class ProfileChangelogItem:
    id: str
    kind: str
    summary: str
    detail: str | None
    source: str
    rationale: str | None
    triggered_by_session_key: str | None
    changed_at: str

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "ProfileChangelogItem":
        return cls(
            id=_as_str(raw.get("id")) or str(uuid4()),
            kind=_as_str(raw.get("kind")) or "constraint_updated",
            summary=_as_str(raw.get("summary")),
            detail=_as_str(raw.get("detail")) or None,
            source=_as_str(raw.get("source")) or "explicit",
            rationale=_as_str(raw.get("rationale")) or None,
            triggered_by_session_key=_as_str(raw.get("triggeredBySessionKey") or raw.get("triggered_by_session_key")) or None,
            changed_at=_as_str(raw.get("changedAt") or raw.get("changed_at")) or utc_now_iso(),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "summary": self.summary,
            "detail": self.detail,
            "source": self.source,
            "rationale": self.rationale,
            "triggeredBySessionKey": self.triggered_by_session_key,
            "changedAt": self.changed_at,
        }


@dataclass(frozen=True)
class BriefingAttentionItem:
    id: str
    title: str
    urgency: str
    source: str
    detail: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "urgency": self.urgency,
            "source": self.source,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class BriefingActivityItem:
    id: str
    summary: str
    session_key: str | None
    tools_used: int | None
    at: str

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "summary": self.summary,
            "sessionKey": self.session_key,
            "toolsUsed": self.tools_used,
            "at": self.at,
        }


@dataclass(frozen=True)
class BriefingWatchItem:
    id: str
    label: str
    signal: str
    source: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "signal": self.signal,
            "source": self.source,
        }


@dataclass(frozen=True)
class ReturnBriefingPayload:
    briefing_id: str
    generated_at: str
    attention_items: list[BriefingAttentionItem] = field(default_factory=list)
    activity_items: list[BriefingActivityItem] = field(default_factory=list)
    watch_items: list[BriefingWatchItem] = field(default_factory=list)
    notice_text: str | None = None
    notice_source: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "briefingId": self.briefing_id,
            "generatedAt": self.generated_at,
            "attentionItems": [item.to_public_dict() for item in self.attention_items],
            "activityItems": [item.to_public_dict() for item in self.activity_items],
            "watchItems": [item.to_public_dict() for item in self.watch_items],
            "noticeText": self.notice_text,
            "noticeSource": self.notice_source,
        }


@dataclass(frozen=True)
class PatProfileBundle:
    profile: PatProfile | None
    identity: dict[str, Any]
    observed_tendencies: list[ObservedTendency]
    guidance_rules: list[GuidanceRule]
    notes_markdown: str
    changelog: list[ProfileChangelogItem]
    overlay_present: bool


class PatProfileService:
    """Loads and maintains the Pat Profile overlay and derived runtime outputs."""

    def __init__(
        self,
        *,
        template_dir: Path | None = None,
        overlay_dir: Path | None = None,
        run_store: RunStore,
    ) -> None:
        self._template_dir = template_dir if template_dir is not None else _profile_template_dir()
        self._overlay_dir = overlay_dir if overlay_dir is not None else default_pat_profile_dir()
        self._run_store = run_store

    def load_bundle(self) -> PatProfileBundle:
        self._ensure_overlay_scaffold()
        template_identity = self._load_template_identity()
        overlay_identity = _read_json(self._overlay_dir / "identity.json", {})
        identity = _merge_dict(template_identity, overlay_identity if isinstance(overlay_identity, dict) else {})
        observed_rows = [
            ObservedTendency.from_json(row)
            for row in _dict_list(_read_json(self._overlay_dir / "observed_tendencies.json", []))
        ]
        guidance_rows = [
            GuidanceRule.from_json(row)
            for row in _dict_list(_read_json(self._overlay_dir / "guidance_rules.json", []))
        ]
        changelog = self.list_changelog(limit=50)
        notes_markdown = _read_markdown(self._overlay_dir / "notes.md", _read_markdown(self._template_dir / "notes.md"))

        overlay_present = bool(identity.get("configured")) or bool(observed_rows or guidance_rows or changelog)
        profile = None
        if overlay_present:
            last_updated = changelog[0].changed_at if changelog else utc_now_iso()
            profile = PatProfile(
                profile_id=_as_str(identity.get("profileId")) or "pat-profile:default",
                display_name=_as_str(identity.get("displayName")) or "Operator",
                active=True,
                source="explicit" if identity.get("configured") else "session_observation",
                priorities=_dict_list(identity.get("priorities")),
                goals=_dict_list(identity.get("goals")),
                tone_preference=dict(identity.get("tonePreference") or {}),
                noise_filters=_string_list(identity.get("noiseFilters")),
                last_updated_at=last_updated,
                changelog_count=len(changelog),
            )

        return PatProfileBundle(
            profile=profile,
            identity=identity,
            observed_tendencies=observed_rows,
            guidance_rules=guidance_rows,
            notes_markdown=notes_markdown,
            changelog=changelog,
            overlay_present=overlay_present,
        )

    def load_profile(self) -> PatProfile | None:
        return self.load_bundle().profile

    def list_changelog(self, *, limit: int = 20) -> list[ProfileChangelogItem]:
        path = self._overlay_dir / "changelog.jsonl"
        if not path.exists():
            return []
        rows: list[ProfileChangelogItem] = []
        for line in reversed(path.read_text(encoding="utf-8").splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(raw, dict):
                rows.append(ProfileChangelogItem.from_json(raw))
            if len(rows) >= limit:
                break
        return rows

    def apply_post_run_updates(self, *, user_message: str, run_record: RunRecord) -> list[ProfileChangelogItem]:
        self._ensure_overlay_scaffold()
        bundle = self.load_bundle()
        identity = dict(bundle.identity)
        tone = dict(identity.get("tonePreference") or {})
        noise_filters = _string_list(identity.get("noiseFilters"))
        guidance = list(bundle.guidance_rules)
        observed = list(bundle.observed_tendencies)
        accepted: list[ProfileChangelogItem] = []
        now = _timestamp_from_record(run_record)
        lower = user_message.lower()

        if "punchline" in lower:
            if tone.get("directness") != "terse":
                tone["directness"] = "terse"
                identity["tonePreference"] = tone
                accepted.append(
                    self._append_changelog(
                        ProfileChangelogItem(
                            id=str(uuid4()),
                            kind="tone_updated",
                            summary="Updated tone preference to lead with the punchline.",
                            detail="User explicitly asked for punchline-first responses.",
                            source="explicit",
                            rationale="Explicit user statement.",
                            triggered_by_session_key=run_record.session_key,
                            changed_at=now,
                        )
                    )
                )
            elif not any("punchline" in item.summary.lower() for item in bundle.changelog[:10]):
                accepted.append(
                    self._append_changelog(
                        ProfileChangelogItem(
                            id=str(uuid4()),
                            kind="tone_updated",
                            summary="Reaffirmed punchline-first tone preference.",
                            detail="User repeated the preference for direct, punchline-first responses.",
                            source="explicit",
                            rationale="Explicit user statement reaffirmed an existing preference.",
                            triggered_by_session_key=run_record.session_key,
                            changed_at=now,
                        )
                    )
                )

        if "china crypto ban" in lower and "ignore" in lower:
            canonical = "ignore china crypto ban headlines unless price moves materially"
            if canonical not in [item.lower() for item in noise_filters]:
                noise_filters.append(canonical)
                identity["noiseFilters"] = noise_filters
                accepted.append(
                    self._append_changelog(
                        ProfileChangelogItem(
                            id=str(uuid4()),
                            kind="noise_filter_added",
                            summary="Added a crypto-ban noise filter.",
                            detail=canonical,
                            source="explicit",
                            rationale="Explicit user filter preference.",
                            triggered_by_session_key=run_record.session_key,
                            changed_at=now,
                        )
                    )
                )

        if "school" in lower and "crypto" in lower and ("push me" in lower or "school before crypto" in lower or "prioritize school" in lower):
            rule_text = "When homework is due tonight, push school before crypto."
            if not any(item.rule == rule_text for item in guidance):
                guidance.append(
                    GuidanceRule(
                        id=str(uuid4()),
                        rule=rule_text,
                        priority="high",
                        source="explicit",
                        rationale="User asked CopeNet to push toward the right thing.",
                        updated_at=now,
                    )
                )
                accepted.append(
                    self._append_changelog(
                        ProfileChangelogItem(
                            id=str(uuid4()),
                            kind="constraint_updated",
                            summary="Added a corrective school-before-crypto rule.",
                            detail=rule_text,
                            source="explicit",
                            rationale="Explicit guidance preference.",
                            triggered_by_session_key=run_record.session_key,
                            changed_at=now,
                        )
                    )
                )

        crypto_mentions = self._recent_keyword_count("crypto")
        if crypto_mentions >= 3 and not any("crypto" in item.label.lower() for item in observed):
            observed.append(
                ObservedTendency(
                    id=str(uuid4()),
                    label="Often foregrounds crypto checks before other tasks.",
                    confidence=0.9,
                    evidence_count=crypto_mentions,
                    source="session_observation",
                    updated_at=now,
                )
            )
            accepted.append(
                self._append_changelog(
                    ProfileChangelogItem(
                        id=str(uuid4()),
                        kind="priority_updated",
                        summary="Observed a recurring crypto-first attention pattern.",
                        detail="Repeated recent runs foregrounded crypto-related asks.",
                        source="session_observation",
                        rationale="Repeated high-confidence pattern.",
                        triggered_by_session_key=run_record.session_key,
                        changed_at=now,
                    )
                )
            )

        if not accepted:
            return []

        identity["configured"] = True
        _write_json(self._overlay_dir / "identity.json", identity)
        _write_json(self._overlay_dir / "observed_tendencies.json", [item.to_json() for item in observed])
        _write_json(self._overlay_dir / "guidance_rules.json", [item.to_json() for item in guidance])
        return accepted

    def build_return_briefing(self) -> ReturnBriefingPayload | None:
        bundle = self.load_bundle()
        runs = self._list_recent_runs(limit=5)
        if not bundle.profile and not bundle.changelog and not runs:
            return None

        attention_items: list[BriefingAttentionItem] = []
        for rule in bundle.guidance_rules[:2]:
            urgency = "high" if rule.priority == "high" else "medium"
            attention_items.append(
                BriefingAttentionItem(
                    id=rule.id,
                    title=rule.rule,
                    urgency=urgency,
                    source="Pat Profile",
                    detail=rule.rationale,
                )
            )

        activity_items = [
            BriefingActivityItem(
                id=record.run_id,
                summary=record.output_summary or record.user_message,
                session_key=record.session_key,
                tools_used=len(record.tool_steps),
                at=record.completed_at or record.started_at,
            )
            for record in runs[:3]
        ]

        watch_items: list[BriefingWatchItem] = []
        for tendency in bundle.observed_tendencies[:2]:
            watch_items.append(
                BriefingWatchItem(
                    id=tendency.id,
                    label=tendency.label,
                    signal=f"Seen {tendency.evidence_count} times recently.",
                    source=tendency.source,
                )
            )

        notice_text = None
        notice_source = None
        if bundle.guidance_rules:
            notice_text = bundle.guidance_rules[0].rule
            notice_source = bundle.guidance_rules[0].source
        elif bundle.observed_tendencies:
            notice_text = bundle.observed_tendencies[0].label
            notice_source = bundle.observed_tendencies[0].source
        elif bundle.changelog:
            notice_text = bundle.changelog[0].summary
            notice_source = bundle.changelog[0].source

        return ReturnBriefingPayload(
            briefing_id=str(uuid4()),
            generated_at=utc_now_iso(),
            attention_items=attention_items,
            activity_items=activity_items,
            watch_items=watch_items,
            notice_text=notice_text,
            notice_source=notice_source,
        )

    def render_session_context(self) -> str | None:
        bundle = self.load_bundle()
        if not bundle.profile:
            return None
        parts = [
            "Pat Profile:",
            f"- Display name: {bundle.profile.display_name}",
        ]
        if bundle.profile.priorities:
            parts.append(
                "- Active priorities: "
                + ", ".join(str(item.get("label") or "").strip() for item in bundle.profile.priorities if str(item.get("label") or "").strip())
            )
        if bundle.profile.goals:
            parts.append(
                "- Current goals: "
                + "; ".join(str(item.get("text") or "").strip() for item in bundle.profile.goals if str(item.get("text") or "").strip())
            )
        if bundle.profile.noise_filters:
            parts.append("- Noise filters: " + "; ".join(bundle.profile.noise_filters))
        if bundle.identity.get("scheduleBasics"):
            parts.append("- Schedule basics: " + "; ".join(_string_list(bundle.identity.get("scheduleBasics"))))
        if bundle.identity.get("recurringConstraints"):
            parts.append("- Recurring constraints: " + "; ".join(_string_list(bundle.identity.get("recurringConstraints"))))
        if bundle.observed_tendencies:
            parts.append("- Observed tendencies: " + "; ".join(item.label for item in bundle.observed_tendencies[:3]))
        if bundle.guidance_rules:
            parts.append("- Guidance rules: " + "; ".join(item.rule for item in bundle.guidance_rules[:3]))
        return "\n".join(parts)

    def _ensure_overlay_scaffold(self) -> None:
        self._overlay_dir.mkdir(parents=True, exist_ok=True)
        template_files = {
            "identity.json": self._template_dir / "identity.json",
            "observed_tendencies.json": self._template_dir / "observed_tendencies.json",
            "guidance_rules.json": self._template_dir / "guidance_rules.json",
            "notes.md": self._template_dir / "notes.md",
        }
        for filename, template_path in template_files.items():
            target = self._overlay_dir / filename
            if not target.exists():
                if filename.endswith(".json"):
                    _write_json(target, _read_json(template_path, {} if filename == "identity.json" else []))
                else:
                    target.write_text(_read_markdown(template_path), encoding="utf-8")
        changelog = self._overlay_dir / "changelog.jsonl"
        if not changelog.exists():
            changelog.write_text("", encoding="utf-8")

    def _load_template_identity(self) -> dict[str, Any]:
        raw = _read_json(self._template_dir / "identity.json", {})
        return dict(raw) if isinstance(raw, dict) else {}

    def _append_changelog(self, item: ProfileChangelogItem) -> ProfileChangelogItem:
        _append_jsonl(self._overlay_dir / "changelog.jsonl", item.to_json())
        return item

    def _recent_keyword_count(self, keyword: str) -> int:
        keyword = keyword.strip().lower()
        if not keyword:
            return 0
        return sum(1 for record in self._list_recent_runs(limit=10) if keyword in record.user_message.lower())

    def _list_recent_runs(self, *, limit: int = 10) -> list[RunRecord]:
        root = Path(self._run_store._root_dir)
        rows: list[RunRecord] = []
        for path in sorted(root.glob("*.jsonl")):
            for record in self._run_store.list_for_session(path.stem, limit=limit):
                rows.append(record)
        rows.sort(key=lambda item: item.completed_at or item.started_at, reverse=True)
        return rows[:limit]
