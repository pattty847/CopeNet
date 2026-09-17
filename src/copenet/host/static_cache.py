"""Cache headers for the served frontend build.

The shell HTML shipped `etag` and `last-modified` but no `Cache-Control`, which is not the
same as "do not cache" — a response with no explicit freshness may be cached heuristically
(RFC 9111 §4.2.2), and browsers commonly take 10% of the age since `Last-Modified`. So the
one file that names the current hashed bundles was held for hours without a request ever
reaching the host. A rebuilt frontend then looked like it had not deployed: `index.html`
came from the browser, pointed at the previous bundle hash, and that bundle was still on
disk and still served happily. iOS was the worst case, because a home-screen web app has no
reload control to break out with.

The split is the standard one, and it is only correct because Vite fingerprints its output:

* `index.html` — revalidate. Not `no-store`: the existing ETag turns the usual case into a
  304 with no body, so correctness here costs one conditional request per load.
* `/assets/*` — `immutable` for a year. The filename carries a content hash, so a changed
  file is a different URL and can never be the stale one.
* PWA root assets and `/imgs` — NOT hashed, so they revalidate like the HTML.
"""

from __future__ import annotations

from typing import Any

from starlette.responses import Response
from starlette.staticfiles import StaticFiles

#: Revalidate on every load. The ETag keeps it cheap; staleness here is what broke deploys.
REVALIDATE = "no-cache, must-revalidate"

#: Safe only for content-hashed filenames.
IMMUTABLE = "public, max-age=31536000, immutable"


def revalidating_headers() -> dict[str, str]:
    """Headers for an un-hashed file whose URL stays the same across builds."""
    return {"Cache-Control": REVALIDATE}


class _CacheControlStaticFiles(StaticFiles):
    """`StaticFiles` that stamps one `Cache-Control` value on every file it serves."""

    cache_control: str

    def file_response(self, *args: Any, **kwargs: Any) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = self.cache_control
        return response


class ImmutableStaticFiles(_CacheControlStaticFiles):
    """For content-hashed bundles, which may be cached forever."""

    cache_control = IMMUTABLE


class RevalidatingStaticFiles(_CacheControlStaticFiles):
    """For assets served under a stable URL across builds."""

    cache_control = REVALIDATE
