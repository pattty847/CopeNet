"""CopeNet host process entry.

Run:
  python -m copenet.host
  # or: copenet-host
"""

from __future__ import annotations

import os

import uvicorn

from copenet.host.api import create_app


def main() -> None:
    host = os.environ.get("COPNET_HOST", os.environ.get("PROMPT_ANYWHERE_HOST", "127.0.0.1"))
    port = int(os.environ.get("COPNET_PORT", os.environ.get("PROMPT_ANYWHERE_PORT", "17123")))

    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
