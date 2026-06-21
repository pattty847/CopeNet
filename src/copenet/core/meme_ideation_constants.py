"""Constants for meme ideation prompts, scoring, and runtime limits."""

from __future__ import annotations


MEME_IDEATION_PRESET_ID = "meme-ideation"
MEME_IDEATION_PROMPT_VERSION = "meme-ideation-v2"
MEME_IDEATION_SCHEMA_VERSION = "v1"
_MAX_REQUESTED_COUNT = 8
_LOCAL_PROVIDER_IDS = {"lm-studio", "ollama"}
_PRESET_ALIASES = {
    "shotgun": MEME_IDEATION_PRESET_ID,
    "sharpshooter": MEME_IDEATION_PRESET_ID,
    "remix": MEME_IDEATION_PRESET_ID,
    "cold-open": MEME_IDEATION_PRESET_ID,
}
_PRESET_GUIDANCE = {
    "shotgun": "Preset mode: shotgun. Push for breadth, divergence, and noticeably different comedic angles.",
    "sharpshooter": "Preset mode: sharpshooter. Favor sharper, more polished candidates and avoid filler variations.",
    "remix": "Preset mode: remix. Riff directly on the provided trend summary or image springboard instead of inventing from nowhere.",
    "cold-open": "Preset mode: cold-open. Build from first principles and do not depend on assumed meme lore or current trend context.",
}
_DOMAIN_COLLISION_BANK = {
    "topical": ("compliance", "finance", "military analysis", "press briefing"),
    "image-shell": ("medical diagnostics", "forensic review", "product QA", "insurance adjuster"),
    "subculture": ("endocrinology", "sports commentary", "eugenics powerpoint", "ritual ranking board"),
    "institutional": ("HR", "consulting", "board meeting", "policy rollout"),
    "political-inversion": ("landlord logic", "corporate subsidy", "national operations memo", "temporary mission management"),
    "cadence-parody": ("sports desk", "trading floor", "podcast clip", "film room breakdown"),
    "default": ("aerospace QA", "religious ritual", "SEC filing", "discharge summary"),
}
_STYLE_ANTI_PATTERNS = (
    "no hashtags",
    "no emoji padding",
    "no broad relatable office humor",
    "no polished slogan copy",
    "no normie explanation",
    "no named mainstream meme templates unless the brief explicitly asks for them",
    "no quirky brand voice",
)
_FAKE_AUTHORITY_WORDS = {
    "protocol",
    "allocation",
    "review",
    "committee",
    "compliance",
    "diagnostic",
    "manager",
    "findings",
    "guidance",
    "memo",
    "forensic",
    "tier",
    "briefing",
    "coverage",
}
_NORMIE_RISK_PHRASES = {
    "just another",
    "adulting",
    "relatable",
    "monday mood",
    "office burnout",
    "when you",
    "the difference between",
    "me trying to",
    "current status",
    "recommend immediate",
    "status update",
    "if you aren't",
    "it started as",
}
_ARTIFACT_FORMATS = {
    "receipt",
    "fortune_cookie",
    "fortune cookie",
    "sticky note",
    "job listing",
    "product label",
    "quote card",
    "image overlay",
    "comment screenshot",
    "protest sign",
    "reaction_caption",
    "tweet_screenshot",
    "screenshot_overlay",
    "screenshot annotation",
    "internal memo",
}
_DOMAIN_KEYWORDS = {
    "finance": {"allocation", "asset", "filing", "equity", "committee", "front-running"},
    "compliance": {"compliance", "review", "policy", "guidance", "flagged"},
    "medical diagnostics": {"diagnostic", "syndrome", "sample", "load", "stress test", "discharge"},
    "forensic review": {"forensic", "evidence", "chain", "artifact", "findings"},
    "product QA": {"sample", "collapse", "stress test", "calibration", "defect"},
    "insurance adjuster": {"claim", "liability", "exposure", "review"},
    "endocrinology": {"cortisol", "low t", "hormonal", "endocrine"},
    "sports commentary": {"film room", "coverage", "line", "completion", "analyst"},
    "eugenics powerpoint": {"phenotype", "metrics", "tier", "slide"},
    "ritual ranking board": {"rite", "initiation", "officiant", "ranking"},
    "HR": {"workplace", "conduct", "manager", "policy", "escalation"},
    "consulting": {"deliverable", "stakeholder", "rollout", "committee"},
    "board meeting": {"board", "agenda", "shareholder", "oversight"},
    "policy rollout": {"pilot", "rollout", "implementation", "memo"},
    "landlord logic": {"tenant", "rent", "maintenance", "notice"},
    "corporate subsidy": {"subsidy", "corporate", "relief", "dependency"},
    "national operations memo": {"operation", "temporary", "region", "escalation"},
    "temporary mission management": {"temporary", "mission", "extension", "coordination"},
    "sports desk": {"desk", "analyst", "tape", "highlight"},
    "trading floor": {"floor", "ticker", "allocation", "filing"},
    "podcast clip": {"clip", "episode", "authority", "panel"},
    "film room breakdown": {"film", "breakdown", "angle", "coverage"},
    "aerospace QA": {"stress test", "load", "flight", "tolerance"},
    "religious ritual": {"rite", "liturgy", "officiant", "blessing"},
    "SEC filing": {"sec", "disclosure", "filing", "committee"},
    "discharge summary": {"discharge", "summary", "evaluation", "acute"},
}
_REWRITE_DETAILS = {
    "aerospace QA": "after the 14-sample load test folded at the tip",
    "religious ritual": "pending minor rite approval",
    "SEC filing": "before the disclosure committee sees it",
    "discharge summary": "pending discharge review",
    "medical diagnostics": "after diagnostic review",
    "forensic review": "per forensic findings",
    "product QA": "once the calibration report lands",
    "insurance adjuster": "after liability review",
    "endocrinology": "pending endocrine review",
    "sports commentary": "after film room review",
    "HR": "per workplace conduct guidance",
    "consulting": "during the rollout window",
    "board meeting": "before it hits the agenda",
    "policy rollout": "during implementation review",
    "compliance": "under compliance review",
    "finance": "before the allocation committee notices",
}
