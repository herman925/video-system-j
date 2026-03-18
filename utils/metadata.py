"""Shared JAV metadata fetching helpers.

All metadata fetches should come through this module so the downloader,
tracker, and cover-fetch flows honor the configured metadata source
consistently. The only cross-fallback concession is when JavLibrary
returns a hard block page such as Cloudflare Error 1015.
"""

from __future__ import annotations

import asyncio

from scraper.javdb import search_javdb_racing
from scraper.javlibrary import JavLibraryHardBlockError, search_javlibrary
from translator.llm import load_config


def resolve_metadata_source(source: str | None = None) -> str:
    """Return the effective metadata source, defaulting to config."""
    if source in {"javdb", "javlibrary"}:
        return source
    return load_config().get("metadata_source", "javdb")


async def _fetch_javdb_with_retry(keyword: str) -> dict:
    """Fetch from JavDB and retry once on the existing 403-style failure path."""
    try:
        return await search_javdb_racing(keyword)
    except Exception as exc:
        if "403" in str(exc):
            await asyncio.sleep(3)
            return await search_javdb_racing(keyword)
        raise


async def fetch_jav_metadata(keyword: str, source: str | None = None) -> dict:
    """
    Fetch JAV metadata using exactly one configured source.

    Behavior:
    - Honors the explicit *source* if provided, otherwise reads config.json
    - Falls back from JavLibrary to JavDB only on explicit hard-block pages
    - Retries JavDB once after a short pause on HTTP 403/rate-limit style errors
    """
    keyword = keyword.strip().upper()
    resolved_source = resolve_metadata_source(source)

    async def _fetch_once() -> dict:
        if resolved_source == "javlibrary":
            return await search_javlibrary(keyword)
        return await _fetch_javdb_with_retry(keyword)

    try:
        return await _fetch_once()
    except JavLibraryHardBlockError as exc:
        if resolved_source != "javlibrary" or exc.reason != "rate limited":
            raise
        print(
            f"[metadata] JAVLibrary hard-blocked for {keyword}: {exc}; falling back to JavDB",
            flush=True,
        )
        return await _fetch_javdb_with_retry(keyword)
    except Exception:
        raise