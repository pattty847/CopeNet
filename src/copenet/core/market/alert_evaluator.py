"""Bounded, offline invocation of the chart's bundled pure indicator registry."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
from typing import Any


def evaluator_request(payload: dict[str, Any]) -> dict[str, Any]:
    node = shutil.which('node')
    bundle = Path(__file__).parents[2] / 'host/frontend/dist/indicator-alerts.cjs'
    if not node or not bundle.is_file():
        raise ValueError('Indicator evaluator unavailable: install Node.js and run the frontend production build')
    body = json.dumps(payload, allow_nan=False)
    if len(body) > 8_000_000:
        raise ValueError('Indicator history exceeds evaluator input limit')
    try:
        result = subprocess.run([node, '--max-old-space-size=128', str(bundle)], input=body,
                                capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('Indicator evaluator unavailable or timed out') from exc
    if len(result.stdout) > 8_000_000:
        raise ValueError('Indicator evaluator output exceeded limit')
    try:
        response = json.loads(result.stdout)
    except ValueError as exc:
        raise ValueError('Indicator evaluator returned invalid output') from exc
    if result.returncode or response.get('error'):
        raise ValueError(response.get('error', 'Indicator evaluator failed'))
    return response


def evaluator_catalogue() -> dict[str, Any]:
    try:
        return {**evaluator_request({'action': 'catalogue'}), 'available': True, 'error': None}
    except ValueError as exc:
        return {'indicators': [], 'available': False, 'error': str(exc)}
