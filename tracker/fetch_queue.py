"""
tracker/fetch_queue.py — Module-level cover-fetch scheduler.

Why module-level?
    Cover fetching is slow (one request every ~2 s via SCRAPER_SEM).  If
    the work lived inside the @ui.page closure, navigating away would leave
    background tasks whose UI callbacks reference deleted elements.  By
    keeping the active-task registry here, tasks outlive any page visit and
    the page just registers lightweight callbacks when it enqueues work.

Deduplication:
    `enqueue()` returns False immediately if a fetch is already running for
    that actress_id, so the caller can notify the user rather than silently
    stacking duplicate jobs.

Callbacks:
    All callbacks are optional and exceptions are silently swallowed, so a
    navigated-away or reloaded page never kills the running fetch loop.

Thread-safety:
    Everything runs in the single asyncio event loop — no locking needed.
"""
from __future__ import annotations

import asyncio
from typing import Callable, Optional

# actress_id → running Task (module-level so it survives page navigation)
_active: dict[str, asyncio.Task] = {}


def is_fetching(actress_id: str) -> bool:
    """True while a cover-fetch batch is running for *actress_id*."""
    t = _active.get(actress_id)
    return t is not None and not t.done()


def enqueue(
    actress_id: str,
    refs: list[str],
    source: str,
    *,
    on_cover_ok: Optional[Callable[[str], None]] = None,
    on_meta: Optional[Callable[[str, dict], None]] = None,
    on_notify: Optional[Callable[[str, str], None]] = None,
    on_done: Optional[Callable[[int, int], None]] = None,
) -> bool:
    """
    Schedule cover fetches for every ref in *refs* (missing ones only).

    Returns True  – a new background task was started.
    Returns False – a fetch is already running for this actress; caller
                    should notify the user instead of queueing another job.

    Callbacks (all optional, exceptions are swallowed):
        on_cover_ok(ref)       called after each ref is successfully cached
        on_meta(ref, meta)     called with full scraper metadata when available;
                               use this to persist actresses/studio/genres for free
                               since the scraper already returns them during a cover fetch
        on_notify(msg, color)  called for start / finish toasts
        on_done(fetched, total) called once after the batch finishes
    """
    if is_fetching(actress_id):
        return False

    task = asyncio.create_task(
        _run(
            actress_id,
            list(refs),
            source,
            on_cover_ok,
            on_meta,
            on_notify,
            on_done,
        ),
        name=f"cover-fetch-{actress_id}",
    )
    _active[actress_id] = task
    return True


# ── internal ──────────────────────────────────────────────────────────────────

def _cb(fn: Optional[Callable], *args) -> None:
    """Call *fn* with *args*, swallowing any exception."""
    if fn is None:
        return
    try:
        fn(*args)
    except Exception:
        pass


def worker_count_for_source(source: str, pending_count: int) -> int:
    """Return the number of parallel fetch workers to run for this batch."""
    try:
        from translator.llm import load_config

        cfg = load_config()
        key = "javlibrary_concurrency" if source == "javlibrary" else "javdb_concurrency"
        configured = max(1, int(cfg.get(key, 1)))
    except Exception:
        configured = 1
    return max(1, min(pending_count, configured))


async def _run(
    actress_id: str,
    refs: list[str],
    source: str,
    on_cover_ok: Optional[Callable[[str], None]],
    on_meta: Optional[Callable[[str, dict], None]],
    on_notify: Optional[Callable[[str, str], None]],
    on_done: Optional[Callable[[int, int], None]],
) -> None:
    from utils.covers import cover_exists, fetch_and_cache_cover
    from utils.metadata import fetch_jav_metadata

    # Re-check which refs still need work — another task may have fetched
    # some while we were waiting to start.
    # A ref needs work if: cover is missing OR metadata title is missing.
    from tracker.store import load_tracker as _lt
    _vd = _lt().get("videos", {})

    def _needs_work(r: str) -> bool:
        if not cover_exists(r):
            return True
        return not bool((_vd.get(r.upper()) or {}).get("_meta", {}).get("title"))

    pending = [r for r in refs if _needs_work(r)]
    if not pending:
        _active.pop(actress_id, None)
        return

    _cb(on_notify, f"Fetching metadata & covers for {len(pending)} release(s) via {source}…", "info")

    fetched = 0
    fetched_lock = asyncio.Lock()
    queue: asyncio.Queue[str] = asyncio.Queue()
    for ref in pending:
        queue.put_nowait(ref)

    async def _worker() -> None:
        nonlocal fetched
        while True:
            try:
                ref = queue.get_nowait()
            except asyncio.QueueEmpty:
                return

            try:
                if cover_exists(ref):
                    # Cover already present — metadata-only fetch.
                    try:
                        meta = await fetch_jav_metadata(ref, source=source)
                    except Exception:
                        meta = None
                    if isinstance(meta, dict) and meta.get("title"):
                        async with fetched_lock:
                            fetched += 1
                        _cb(on_meta, ref, meta)
                else:
                    ok, meta = await fetch_and_cache_cover(ref, source=source)
                    if ok or meta:
                        async with fetched_lock:
                            fetched += 1
                    if ok:
                        _cb(on_cover_ok, ref)
                    if meta:
                        _cb(on_meta, ref, meta)
            finally:
                queue.task_done()

    worker_count = worker_count_for_source(source, len(pending))
    print(
        f"[COVER][tracker] Starting {worker_count} worker(s) for {len(pending)} pending ref(s) via {source}",
        flush=True,
    )
    await asyncio.gather(*(_worker() for _ in range(worker_count)))

    _active.pop(actress_id, None)
    _cb(on_done, fetched, len(pending))

    if fetched:
        _cb(on_notify, f"Data fetched: {fetched}/{len(pending)} via {source}", "positive")
    elif pending:
        _cb(on_notify, f"No data retrieved (0/{len(pending)})", "warning")
