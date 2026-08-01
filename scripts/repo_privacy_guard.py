"""Fail closed when tracked content contains local secrets or operator-private data markers.

The guard never prints a secret value. Run it before every push; the repository-local pre-push
hook invokes it automatically on this checkout.
"""

from __future__ import annotations

import os
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parent.parent
ALLOWED_ENV_SUFFIXES = (".example", ".sample", ".template")
SENSITIVE_KEY = re.compile(r"(?i)(token|secret|password|passwd|passphrase|api[_-]?key|private[_-]?key|credential|trade[_-]?pin)")
PRIVATE_ACCOUNT_KEY = re.compile(
    r"(?i)(account.*id|account.*number|order.*id|avg.*cost|quantity|market.*value|total.*equity|"
    r"cash|buying.*power|unrealized|realized|filled.*price|filled.*quantity)"
)
PERSONAL_CONTENT = (
    (re.compile(rb"/Users/(?!example(?:/|$))[^/\s]+/"), "personal macOS home path"),
    (re.compile(rb"(?i)\b[A-Z0-9._%+-]+@gmail\.com\b"), "personal Gmail address"),
    (re.compile(rb"(?i)\b(actual book|current live figure|live account before this|operator's real Webull lists)\b"), "live-account prose"),
)
PRIVATE_BROKER_NAMES = {"account.json", "portfolio.json", "orders.json", "token.txt"}
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".woff", ".woff2", ".ttf"}


def _tracked_paths() -> list[str]:
    output = subprocess.check_output(["git", "ls-files", "-z"], cwd=REPO_ROOT)
    return [item.decode("utf-8", errors="surrogateescape") for item in output.split(b"\0") if item]


def _is_forbidden_path(path: str) -> str | None:
    pure = PurePosixPath(path)
    name = pure.name.lower()
    if name.startswith(".env") and not name.endswith(ALLOWED_ENV_SUFFIXES):
        return "environment file"
    if "webull" in {part.lower() for part in pure.parts} and name in PRIVATE_BROKER_NAMES:
        return "broker account data"
    if name in {"portfolio-export.csv", "holdings-export.csv", "transactions-export.csv", "fills-export.csv"}:
        return "financial export"
    if name.endswith((".pem", ".p12", ".pfx", ".jks")):
        return "private credential file"
    return None


def _local_secrets() -> dict[bytes, set[str]]:
    found: dict[bytes, set[str]] = {}
    env_paths = (
        REPO_ROOT / ".env",
        REPO_ROOT / ".env.local",
        REPO_ROOT / ".copenet.env",
        REPO_ROOT / "src/copenet/host/frontend/.env",
    )
    for path in env_paths:
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value_bytes = value.strip().strip("\"'").encode()
            if SENSITIVE_KEY.search(key) and len(value_bytes) >= 8 and value_bytes.lower() not in {b"dev-token", b"test-token"}:
                found.setdefault(value_bytes, set()).add(f"{path.name}:{key.strip()}")

    token_file = Path(os.environ.get("COPNET_HOME", Path.home() / ".copenet")) / "data/market/webull/token/token.txt"
    if token_file.exists():
        first_line = token_file.read_bytes().splitlines()[:1]
        if first_line and len(first_line[0].strip()) >= 8:
            found.setdefault(first_line[0].strip(), set()).add("local Webull SDK token")

    webull_root = token_file.parent.parent
    for path in (webull_root / "account.json", webull_root / "portfolio.json", webull_root / "orders.json"):
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        def collect(value: object, trail: str = "") -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    next_trail = f"{trail}.{key}" if trail else str(key)
                    if PRIVATE_ACCOUNT_KEY.search(str(key)) and isinstance(item, (str, int, float)):
                        raw = str(item).encode()
                        distinctive_number = isinstance(item, (int, float)) and (len(raw) >= 6 or abs(float(item)) >= 10_000)
                        if (isinstance(item, str) and len(raw) >= 8) or distinctive_number:
                            found.setdefault(raw, set()).add(f"local Webull data:{next_trail}")
                    collect(item, next_trail)
            elif isinstance(value, list):
                for item in value:
                    collect(item, trail)

        collect(payload)
    return found


def main() -> int:
    errors: list[str] = []
    tracked = _tracked_paths()
    secrets = _local_secrets()
    for relative in tracked:
        reason = _is_forbidden_path(relative)
        if reason:
            errors.append(f"{relative}: tracked {reason}")
            continue
        path = REPO_ROOT / relative
        if path.suffix.lower() in BINARY_SUFFIXES:
            continue
        try:
            content = path.read_bytes()
        except OSError:
            continue
        if relative != "scripts/repo_privacy_guard.py":
            for pattern, label in PERSONAL_CONTENT:
                if pattern.search(content):
                    errors.append(f"{relative}: contains {label}")
        for value, labels in secrets.items():
            if value in content:
                errors.append(f"{relative}: contains local secret from {', '.join(sorted(labels))}")

    if errors:
        print("Repository privacy guard failed (secret values are redacted):", file=sys.stderr)
        for error in sorted(set(errors)):
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Repository privacy guard passed: {len(tracked)} tracked files; {len(secrets)} local sensitive value(s) checked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
