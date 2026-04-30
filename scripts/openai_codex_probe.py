"""Probe the raw OpenAI Codex responses transport used by CopeNet.

This script is intentionally low-level. It authenticates with CopeNet's local
openai-codex auth store, sends one request to the Codex responses backend, and
prints the raw HTTP shape so we can debug transport/parser mismatches.
"""

from __future__ import annotations

import argparse
import json
from typing import Any
from urllib import error, request

from copenet.core.provider_auth import OpenAICodexAuthService
from copenet.providers.openai_codex import OPENAI_CODEX_BASE_URL


def build_payload(*, model: str, prompt: str, system_prompt: str | None, stream: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": prompt or " "}],
            }
        ],
        "store": False,
        "stream": stream,
        "text": {"verbosity": "medium"},
    }
    if system_prompt and system_prompt.strip():
        payload["instructions"] = system_prompt.strip()
    return payload


def build_headers(*, access_token: str, account_id: str | None, accept: str) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": accept,
        "originator": "copenet",
        "User-Agent": "copenet",
    }
    if account_id:
        headers["ChatGPT-Account-Id"] = account_id
    return headers


def preview_text(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return f"{value[:max_chars]}...<truncated>"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--prompt", default="Say OK.")
    parser.add_argument("--system-prompt", default="")
    parser.add_argument("--stream", action="store_true", help="Send stream=true and request text/event-stream.")
    parser.add_argument("--preview-chars", type=int, default=1200)
    parser.add_argument("--save-body", default="", help="Optional file path for the raw response body.")
    args = parser.parse_args()

    auth = OpenAICodexAuthService()
    profile = auth.ensure_valid_profile()
    payload = build_payload(
        model=args.model,
        prompt=args.prompt,
        system_prompt=args.system_prompt or None,
        stream=args.stream,
    )
    accept = "text/event-stream" if args.stream else "application/json"
    req = request.Request(
        f"{OPENAI_CODEX_BASE_URL}/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers=build_headers(access_token=profile.access_token, account_id=profile.account_id, accept=accept),
        method="POST",
    )

    print("== Request ==")
    print(json.dumps({"url": req.full_url, "payload": payload, "accept": accept}, indent=2))
    print()

    try:
        with request.urlopen(req, timeout=120.0) as response:
            body = response.read().decode("utf-8", errors="replace")
            status = response.status
            headers = dict(response.headers.items())
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print("== HTTP Error ==")
        print(f"status: {exc.code}")
        print(f"reason: {exc.reason}")
        print("headers:")
        for key, value in exc.headers.items():
            print(f"  {key}: {value}")
        print("body preview:")
        print(preview_text(body, args.preview_chars))
        if args.save_body:
            with open(args.save_body, "w", encoding="utf-8") as fh:
                fh.write(body)
            print(f"\nsaved raw body to {args.save_body}")
        return 1
    except error.URLError as exc:
        print(f"transport error: {exc.reason}")
        return 1

    print("== Response ==")
    print(f"status: {status}")
    print("headers:")
    for key, value in headers.items():
        print(f"  {key}: {value}")
    print(f"body length: {len(body)}")
    print("body preview:")
    print(preview_text(body, args.preview_chars))

    if args.save_body:
        with open(args.save_body, "w", encoding="utf-8") as fh:
            fh.write(body)
        print(f"\nsaved raw body to {args.save_body}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
