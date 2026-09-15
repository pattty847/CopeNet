#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
with_sec=0

if [[ "${1:-}" == "--with-sec" ]]; then
  with_sec=1
elif [[ -n "${1:-}" ]]; then
  echo "Usage: ./scripts/setup.sh [--with-sec]" >&2
  exit 2
fi

for command_name in uv npm; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Missing prerequisite: $command_name is not on PATH." >&2
    exit 1
  fi
done

cd "$repo_root"

if (( with_sec )); then
  echo "Installing CopeNet with optional SEC fundamentals and filings support..."
  uv sync --extra dev --extra sec
else
  echo "Installing CopeNet core..."
  uv sync --extra dev
fi

echo "Installing and building the operator UI..."
npm ci --prefix src/copenet/host/frontend
npm run build --prefix src/copenet/host/frontend

echo
echo "CopeNet is installed. Start it with:"
echo "  uv run copenet"
echo
echo "Then open http://127.0.0.1:17123 and finish provider setup on Home."
if (( ! with_sec )); then
  echo "SEC filings, fundamentals, and insider evidence are disabled."
  echo "Enable them later with: ./scripts/setup.sh --with-sec"
fi
