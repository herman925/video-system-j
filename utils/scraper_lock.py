"""
Shared scraper rate-limiting lock.

Imported by both main.py (metadata scrapes) and utils/covers.py (cover
fetches) so that all outbound JAV scraper requests are serialised and
rate-limited through the same single-slot lock.

SCRAPER_SEM is an async context manager that:
  • allows only one request at a time (like asyncio.Semaphore(1))
  • enforces a mandatory cooldown between consecutive releases so that
    rapid re-acquisition after an unlock still waits the right amount,
    protecting against rate-limits even when multiple callers compete
    (e.g. cover fetches for two actresses interleaved with a downloader
    metadata fetch).

The cooldown is measured from the *release* of the previous holder, so
the gap is: (time waiting for sem) + (cooldown remaining).  In practice
this means at most one outbound javdb/javlibrary request every ~2 s
across the entire app.
"""
import asyncio
import time


class _ScraperLock:
    """One request at a time + mandatory cooldown between releases."""

    def __init__(self, cooldown: float = 2.0) -> None:
        self._sem = asyncio.Semaphore(1)
        self._cooldown = cooldown
        self._last_release: float = 0.0

    async def __aenter__(self) -> "_ScraperLock":
        await self._sem.acquire()
        # Wait out any remaining cooldown from the previous release.
        remaining = self._cooldown - (time.monotonic() - self._last_release)
        if remaining > 0:
            await asyncio.sleep(remaining)
        return self

    async def __aexit__(self, *_) -> None:
        self._last_release = time.monotonic()
        self._sem.release()


# One outbound scraper request at a time across ALL modules,
# with a 2-second cooldown between consecutive requests.
SCRAPER_SEM = _ScraperLock(cooldown=2.0)
