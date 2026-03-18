"""
Scraper for javlibrary.com using nodriver (undetected Chrome).

nodriver launches Chrome with all automation signals stripped, then
auto-clicks Cloudflare challenges.  A persistent Chrome profile stores the
resulting cf_clearance cookie, so the challenge only fires once — all
subsequent searches open and close in a second or two.
"""
import asyncio
import copy
import hashlib
import traceback
from pathlib import Path
import re
import requests as std_requests
import time
from urllib.parse import urljoin, parse_qs, urlparse
from typing import Any, Awaitable, Callable, Dict

import nodriver as uc
from bs4 import BeautifulSoup

from utils.paths import CHROME_PROFILE_DIR

JAVLIBRARY_BASE   = "https://www.javlibrary.com/tw/"
JAVLIBRARY_SEARCH = JAVLIBRARY_BASE + "vl_searchbyid.php?keyword={}"

# Saved here so cf_clearance survives between app restarts
_PROFILE_DIR = str(CHROME_PROFILE_DIR)


_CONTENT_SELECTORS = ("#video_jacket", ".videos .video", "#video_title")
_CLOUDFLARE_SIGNALS = ("Just a moment", "cf-browser-verification", "Enable JavaScript")
_HARD_BLOCK_SIGNALS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("error 1015",), "rate limited"),
    (("you are being rate limited",), "rate limited"),
    (("has banned you temporarily",), "rate limited"),
    (("error 1020",), "access denied"),
    (("cloudflare", "access denied"), "access denied"),
)

# Fast polling while the page is making normal progress.
_POLL_INTERVAL = 3
# Once we know the browser is blocked on Cloudflare/user intervention,
# back off so we do not hammer the page while still waiting indefinitely.
_BLOCKED_POLL_INTERVAL = 10
_DEFAULT_FOREGROUND_DELAY = float(_POLL_INTERVAL)
_RATE_LIMIT_COOLDOWN_SECONDS = 60.0
_MAX_DEFERRED_RETRY_ATTEMPTS = 3

# Politeness delay between page navigations inside a single browser session.
_PAGE_DELAY = 1.5  # seconds

# ── Browser profile pool ──────────────────────────────────────────────────────
# Each concurrent browser needs its own profile dir to avoid Chrome state
# conflicts.  Pool is a queue of profile-dir strings; checked out before
# starting a browser and returned after stopping it.
#
# Slot 0  —  original CHROME_PROFILE_DIR  (preserves existing cf_clearance)
# Slot N  —  CHROME_PROFILE_DIR/slot_N    (needs first-run CF solve)
#
# Pool size = javlibrary_concurrency from config (default 1).

_BROWSER_POOL: "asyncio.Queue[str] | None" = None
_pool_init_lock: "asyncio.Lock | None" = None
_rate_limit_lock: "asyncio.Lock | None" = None
_rate_limit_until: float = 0.0
_pending_rate_limited_retries: dict[str, asyncio.Task] = {}
_deferred_retry_results: dict[str, Any] = {}


class JavLibraryHardBlockError(RuntimeError):
    """Raised when JavLibrary returns a hard block page instead of a solvable challenge."""

    def __init__(self, *, context: str | None = None, reason: str | None = None):
        details = "JAVLibrary returned a hard block page"
        if context:
            details += f" for {context}"
        if reason:
            details += f" ({reason})"
        super().__init__(details)
        self.context = context
        self.reason = reason


def _get_rate_limit_lock() -> asyncio.Lock:
    global _rate_limit_lock
    if _rate_limit_lock is None:
        _rate_limit_lock = asyncio.Lock()
    return _rate_limit_lock


def _cooldown_remaining() -> float:
    return max(0.0, _rate_limit_until - time.monotonic())


def get_rate_limit_cooldown_seconds(exc: BaseException | None = None) -> int | None:
    """Return remaining cooldown seconds when a JavLibrary rate-limit state is active."""
    reason = getattr(exc, "reason", None)
    remaining = _cooldown_remaining()
    if reason == "rate limited" or remaining > 0:
        return max(1, int(remaining + 0.999))
    return None


def _consume_deferred_retry_result(retry_key: str) -> Any | None:
    if retry_key not in _deferred_retry_results:
        return None
    return copy.deepcopy(_deferred_retry_results.pop(retry_key))


async def _activate_rate_limit_cooldown(context: str) -> None:
    global _rate_limit_until
    async with _get_rate_limit_lock():
        _rate_limit_until = max(
            _rate_limit_until,
            time.monotonic() + _RATE_LIMIT_COOLDOWN_SECONDS,
        )
    print(
        f"[JAVLIBRARY] rate limit cooldown active for {context}; delaying new JavLibrary work for {_cooldown_remaining():.1f}s",
        flush=True,
    )


def _schedule_rate_limited_retry(
    retry_key: str,
    context: str,
    operation: Callable[[], Awaitable[Any]],
) -> None:
    if retry_key in _pending_rate_limited_retries:
        return

    async def _runner() -> None:
        try:
            attempts = 0
            while attempts < _MAX_DEFERRED_RETRY_ATTEMPTS:
                remaining = _cooldown_remaining()
                if remaining > 0:
                    print(
                        f"[JAVLIBRARY] deferred retry queued for {context}; waiting {remaining:.1f}s",
                        flush=True,
                    )
                    await asyncio.sleep(remaining)

                attempts += 1
                try:
                    result = await operation()
                except JavLibraryHardBlockError as exc:
                    if exc.reason == "rate limited":
                        await _activate_rate_limit_cooldown(context)
                        print(
                            f"[JAVLIBRARY] deferred retry still rate limited for {context}; re-queueing",
                            flush=True,
                        )
                        continue
                    print(
                        f"[JAVLIBRARY] deferred retry aborted for {context}: {exc}",
                        flush=True,
                    )
                    return
                except Exception as exc:
                    print(
                        f"[JAVLIBRARY] deferred retry failed for {context}: {exc}",
                        flush=True,
                    )
                    return

                _deferred_retry_results[retry_key] = copy.deepcopy(result)
                print(f"[JAVLIBRARY] deferred retry succeeded for {context}", flush=True)
                return
        finally:
            _pending_rate_limited_retries.pop(retry_key, None)

    _pending_rate_limited_retries[retry_key] = asyncio.create_task(
        _runner(),
        name=f"javlibrary-rate-limit-retry-{retry_key}",
    )


async def _raise_or_defer_for_active_cooldown(
    retry_key: str,
    context: str,
    operation: Callable[[], Awaitable[Any]],
) -> None:
    remaining = _cooldown_remaining()
    if remaining <= 0:
        return
    _schedule_rate_limited_retry(retry_key, context, operation)
    print(
        f"[JAVLIBRARY] cooldown already active; deferring {context} for {remaining:.1f}s",
        flush=True,
    )
    raise JavLibraryHardBlockError(context=context, reason="rate limited")


async def _handle_rate_limited_operation(
    retry_key: str,
    context: str,
    operation: Callable[[], Awaitable[Any]],
) -> Any:
    cached = _consume_deferred_retry_result(retry_key)
    if cached is not None:
        print(f"[JAVLIBRARY] using deferred retry result for {context}", flush=True)
        return cached

    pending_retry = _pending_rate_limited_retries.get(retry_key)
    if pending_retry is not None and _cooldown_remaining() <= 0:
        print(
            f"[JAVLIBRARY] awaiting in-flight deferred retry for {context}",
            flush=True,
        )
        await asyncio.shield(pending_retry)
        cached = _consume_deferred_retry_result(retry_key)
        if cached is not None:
            print(f"[JAVLIBRARY] using deferred retry result for {context}", flush=True)
            return cached

    await _raise_or_defer_for_active_cooldown(retry_key, context, operation)

    try:
        return await operation()
    except JavLibraryHardBlockError as exc:
        if exc.reason == "rate limited":
            await _activate_rate_limit_cooldown(context)
            _schedule_rate_limited_retry(retry_key, context, operation)
        raise


def _actress_id_from_url(url: str) -> str:
    qs = parse_qs(urlparse(url).query)
    return (qs.get("s") or [""])[0]


def _known_refs_fingerprint(known_refs: set[str] | None) -> str:
    if known_refs is None:
        return "all"
    normalized = sorted(str(ref).strip().upper() for ref in known_refs if str(ref).strip())
    digest = hashlib.sha1("\n".join(normalized).encode("utf-8")).hexdigest()
    return digest


def _get_pool_lock() -> asyncio.Lock:
    global _pool_init_lock
    if _pool_init_lock is None:
        _pool_init_lock = asyncio.Lock()
    return _pool_init_lock


async def _ensure_browser_pool() -> "asyncio.Queue[str]":
    """Return the profile pool, initialising it lazily from config."""
    global _BROWSER_POOL
    if _BROWSER_POOL is not None:
        return _BROWSER_POOL
    async with _get_pool_lock():
        if _BROWSER_POOL is None:
            try:
                from translator.llm import load_config
                n = max(1, int(load_config().get("javlibrary_concurrency", 1)))
            except Exception:
                n = 1
            q: asyncio.Queue = asyncio.Queue()
            for i in range(n):
                profile = (
                    _PROFILE_DIR if i == 0
                    else str(CHROME_PROFILE_DIR / f"slot_{i}")
                )
                q.put_nowait(profile)
            _BROWSER_POOL = q
    return _BROWSER_POOL


def reset_browser_pool() -> None:
    """Reset the pool so it re-initialises from config on next use."""
    global _BROWSER_POOL
    _BROWSER_POOL = None


def _looks_cloudflare_blocked(html: str, soup: BeautifulSoup) -> bool:
    """Best-effort detection that the page is waiting on Cloudflare/user input."""
    visible_text = " ".join(soup.get_text(" ", strip=True).split())
    haystack = f"{html}\n{visible_text}".lower()
    return any(signal.lower() in haystack for signal in _CLOUDFLARE_SIGNALS)


def _get_hard_block_reason(html: str, soup: BeautifulSoup) -> str | None:
    """Return the block reason when Cloudflare serves a hard-stop page."""
    visible_text = " ".join(soup.get_text(" ", strip=True).split())
    haystack = f"{html}\n{visible_text}".lower()
    for terms, reason in _HARD_BLOCK_SIGNALS:
        if all(term in haystack for term in terms):
            return reason
    return None


def _get_foreground_delay() -> float:
    try:
        from translator.llm import load_config

        return max(0.0, float(load_config().get("javlibrary_foreground_delay", _DEFAULT_FOREGROUND_DELAY)))
    except Exception:
        return _DEFAULT_FOREGROUND_DELAY


async def _bring_window_onscreen(tab) -> None:
    """Restore the active Chrome tab window to a visible on-screen position."""
    try:
        await tab.set_window_state(left=80, top=60, width=1360, height=900, state="normal")
    except Exception:
        try:
            await tab.set_window_size(left=80, top=60, width=1360, height=900)
        except Exception:
            pass

    try:
        await tab.bring_to_front()
    except Exception:
        try:
            await tab.activate()
        except Exception:
            pass

    try:
        await asyncio.sleep(0.15)
        await tab.bring_to_front()
    except Exception:
        pass


async def _wait_for_content(tab, browser=None, *, context: str | None = None) -> "BeautifulSoup | None":
    """
    Poll the tab until real javlibrary content appears.

    Cloudflare detection switches to slower polling (to reduce load) but does
    NOT surface the window — Chrome only comes to the foreground once the
    configured foreground_delay has elapsed without content appearing.
    """
    del browser  # kept for backward-compatible call sites

    slow_poll = False       # True → use _BLOCKED_POLL_INTERVAL (CF detected)
    brought_onscreen = False  # True → Chrome already surfaced (delay elapsed)
    attempt = 0
    started_at = asyncio.get_running_loop().time()
    foreground_delay = _get_foreground_delay()
    print(
        f"[JAVLIBRARY] _wait_for_content: foreground_delay={foreground_delay:.1f}s  "
        f"poll={_POLL_INTERVAL}s  blocked_poll={_BLOCKED_POLL_INTERVAL}s",
        flush=True,
    )
    while True:
        attempt += 1
        html = await tab.get_content()
        soup = BeautifulSoup(html, "html.parser")
        elapsed = asyncio.get_running_loop().time() - started_at

        if any(soup.select_one(sel) for sel in _CONTENT_SELECTORS):
            print(f"[JAVLIBRARY] content found at attempt {attempt} ({elapsed:.1f}s elapsed)", flush=True)
            return soup  # real content found

        print(
            f"[JAVLIBRARY] attempt {attempt}: elapsed={elapsed:.1f}s  "
            f"cf_blocked={slow_poll}  brought_onscreen={brought_onscreen}  "
            f"foreground_at={foreground_delay:.1f}s",
            flush=True,
        )

        block_reason = _get_hard_block_reason(html, soup)
        if block_reason:
            print(
                f"[JAVLIBRARY] hard block detected at {elapsed:.1f}s ({block_reason})",
                flush=True,
            )
            raise JavLibraryHardBlockError(context=context, reason=block_reason)

        # CF detected → back off polling to reduce load, but keep Chrome hidden.
        if not slow_poll and _looks_cloudflare_blocked(html, soup):
            slow_poll = True
            print(f"[JAVLIBRARY] Cloudflare challenge detected at {elapsed:.1f}s", flush=True)

        # Only surface Chrome after the user-configured delay has elapsed.
        if not brought_onscreen and elapsed >= foreground_delay:
            slow_poll = True
            brought_onscreen = True
            await _bring_window_onscreen(tab)
            print(
                f"[JAVLIBRARY] Search page needs user intervention at {elapsed:.1f}s; "
                f"surfacing Chrome window and switching to {_BLOCKED_POLL_INTERVAL}s polling",
                flush=True,
            )

        await asyncio.sleep(_BLOCKED_POLL_INTERVAL if slow_poll else _POLL_INTERVAL)


async def _wait_for_actress_content(tab, browser=None, *, context: str | None = None) -> "BeautifulSoup | None":
    """
    Wait for an actress listing page to load.

    Accepts the page only when '所演出的影片' is present in the page text —
    this heading is always on actress listing pages and never on Cloudflare
    challenge pages or intermediate loading states.
    """
    del browser  # kept for backward-compatible call sites

    slow_poll = False       # True → use _BLOCKED_POLL_INTERVAL (CF detected)
    brought_onscreen = False  # True → Chrome already surfaced (delay elapsed)
    attempt = 0
    started_at = asyncio.get_running_loop().time()
    foreground_delay = _get_foreground_delay()
    print(
        f"[TRACKER] _wait_for_actress_content: foreground_delay={foreground_delay:.1f}s  "
        f"poll={_POLL_INTERVAL}s  blocked_poll={_BLOCKED_POLL_INTERVAL}s",
        flush=True,
    )
    while True:
        attempt += 1
        html = await tab.get_content()
        elapsed = asyncio.get_running_loop().time() - started_at
        print(f"[TRACKER] attempt {attempt}: elapsed={elapsed:.1f}s  html_len={len(html)}  "
              f"has_heading={'所演出的影片' in html}  brought_onscreen={brought_onscreen}  "
              f"url={tab.url!r:.80}", flush=True)

        # Check the raw HTML for the actress heading
        if "所演出的影片" in html:
            print("[TRACKER] actress heading found — page ready", flush=True)
            return BeautifulSoup(html, "html.parser")

        # Print first 300 chars of visible text to show what Chrome is showing
        soup_dbg = BeautifulSoup(html, "html.parser")
        snippet = " ".join(soup_dbg.get_text().split())[:300]
        print(f"[TRACKER] page text snippet: {snippet!r}", flush=True)

        block_reason = _get_hard_block_reason(html, soup_dbg)
        if block_reason:
            print(
                f"[TRACKER] hard block detected at {elapsed:.1f}s ({block_reason})",
                flush=True,
            )
            raise JavLibraryHardBlockError(context=context, reason=block_reason)

        # CF detected → back off polling to reduce load, but keep Chrome hidden.
        if not slow_poll and _looks_cloudflare_blocked(html, soup_dbg):
            slow_poll = True
            print(f"[TRACKER] Cloudflare challenge detected at {elapsed:.1f}s", flush=True)

        # Only surface Chrome after the user-configured delay has elapsed.
        if not brought_onscreen and elapsed >= foreground_delay:
            slow_poll = True
            brought_onscreen = True
            await _bring_window_onscreen(tab)
            print(
                f"[TRACKER] Actress page needs user intervention at {elapsed:.1f}s; "
                f"surfacing Chrome window and switching to {_BLOCKED_POLL_INTERVAL}s polling",
                flush=True,
            )

        await asyncio.sleep(_BLOCKED_POLL_INTERVAL if slow_poll else _POLL_INTERVAL)




def _parse_detail(soup: BeautifulSoup) -> Dict:
    """Extract metadata fields from a parsed javlibrary detail page."""
    result: Dict = {}

    el = soup.select_one("#video_title h3.post-title")
    if el:
        result["title"] = el.get_text(strip=True)

    el = soup.select_one("#video_jacket img")
    if el:
        src = el.get("src", "")
        if src.startswith("//"):
            src = "https:" + src
        result["cover_url"] = src

    el = soup.select_one("#video_id .text")
    if el:
        result["id"] = el.get_text(strip=True)

    el = soup.select_one("#video_date .text")
    if el:
        result["date"] = el.get_text(strip=True)

    el = soup.select_one("#video_maker .text a")
    if el:
        result["studio"] = el.get_text(strip=True)

    result["actresses"] = [
        e.get_text(strip=True) for e in soup.select("#video_cast .star a")
    ]
    result["genres"] = [
        e.get_text(strip=True) for e in soup.select("#video_genres .genre a")
    ]

    return result


async def _search_javlibrary_impl(keyword: str) -> Dict:
    """
    Search javlibrary.com for *keyword* (e.g. "WAAA-622").

    On first run Chrome may open briefly to solve a Cloudflare challenge.
    The cookie is then saved to chrome_profile/ so every run after that
    is instant (window opens and closes in ~1 second).

    When javlibrary_concurrency > 1 in config, multiple keyword lookups
    run in parallel, each using its own Chrome profile slot so they never
    conflict.  Slot-0 is always the original profile (existing cf_clearance).
    """
    pool = await _ensure_browser_pool()
    print(f"[JAVLIBRARY] [{keyword}] pool acquired, waiting for profile slot …", flush=True)
    profile_dir = await pool.get()
    print(f"[JAVLIBRARY] [{keyword}] got profile: {profile_dir}", flush=True)

    print(f"[JAVLIBRARY] [{keyword}] calling uc.start() …", flush=True)
    try:
        browser = await uc.start(
            user_data_dir=profile_dir,
            headless=False,
            browser_args=[
                "--window-size=1280,800",
                "--window-position=-32000,-32000",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )
    except Exception:
        print(f"[JAVLIBRARY] [{keyword}] uc.start() FAILED:\n{traceback.format_exc()}", flush=True)
        pool.put_nowait(profile_dir)
        raise
    print(f"[JAVLIBRARY] [{keyword}] browser started OK", flush=True)

    try:
        url = JAVLIBRARY_SEARCH.format(keyword)
        print(f"[JAVLIBRARY] [{keyword}] browser.get({url!r}) …", flush=True)
        try:
            tab = await browser.get(url)
        except Exception:
            print(f"[JAVLIBRARY] [{keyword}] browser.get() FAILED:\n{traceback.format_exc()}", flush=True)
            raise
        print(f"[JAVLIBRARY] [{keyword}] page loaded, entering _wait_for_content …", flush=True)

        # Poll until real content appears — gives the user time to solve any
        # Cloudflare challenge that appears in the browser window.
        soup = await _wait_for_content(tab, browser, context=keyword)

        # ── Search results grid ───────────────────────────────────────────────
        videos = soup.select(".videos .video")
        if videos:
            target_href = None
            for video in videos:
                id_el = video.select_one(".id")
                if id_el and id_el.get_text(strip=True).upper() == keyword.upper():
                    a = video.select_one("a")
                    target_href = a["href"] if a else None
                    break
            if not target_href:
                a = videos[0].select_one("a")
                target_href = a["href"] if a else None

            if target_href:
                detail_url = urljoin(JAVLIBRARY_BASE, target_href)
                tab = await browser.get(detail_url)
                soup = await _wait_for_content(tab, browser, context=keyword)

        # ── Verify we're on a detail page ────────────────────────────────────
        if not soup.select_one("#video_jacket"):
            raise ValueError(f"No results found for '{keyword}' on javlibrary.com")

        result = _parse_detail(soup)

        # ── Save cover to shared file cache ───────────────────────────────────
        cover_url = result.get("cover_url", "")
        if cover_url:
            try:
                from utils.covers import save_cover_bytes
                print(f"[COVER][javlibrary] Downloading cover for {keyword} …", flush=True)
                r = std_requests.get(
                    cover_url,
                    headers={
                        "Referer": JAVLIBRARY_BASE,
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    },
                    timeout=10,
                )
                if r.ok:
                    ext = Path(cover_url.split("?")[0]).suffix or ".jpg"
                    save_cover_bytes(keyword, r.content, ext)
                    print(f"[COVER][javlibrary] ✓ {keyword} Cover{ext} ({len(r.content):,} bytes)", flush=True)
                else:
                    print(f"[COVER][javlibrary] ✗ HTTP {r.status_code} for {keyword}", flush=True)
            except Exception as _e:
                print(f"[COVER][javlibrary] ✗ {keyword}: {_e}", flush=True)

        return result

    finally:
        try:
            browser.stop()
        finally:
            pool.put_nowait(profile_dir)


# ── Actress page scraping ──────────────────────────────────────────────────────

def _parse_actress_text_page(soup: BeautifulSoup, base_url: str) -> tuple[str, list[dict]]:
    """
    Parse a javlibrary text-mode actress listing page.

    URL form: vl_star.php?list&mode=&s={actress_id}&page={n}

    Confirmed page structure:
    - Actress name: <div class="boxtitle">NAME 所演出的影片</div>
    - Video table: <table class="videotextlist">
      - Header row: <tr class="header"> (skip)
      - Video rows: <tr> / <tr class="dimrow">
        - col 0 <td class="title">: contains <div class="video"> with toolbar <a> tags
          (no href) and the actual video <a href="./ID.html">REF-123 Title</a>
        - col 1 <td>: YYYY-MM-DD release date
        - col 2, 3: comment counts (ignored)

    Returns (actress_name, videos_list).
    """
    # ── Actress name ──────────────────────────────────────────────────────────
    name = ""
    boxtitle = soup.select_one(".boxtitle")
    if boxtitle:
        text = boxtitle.get_text(strip=True)
        if "所演出的影片" in text:
            name = text.replace("所演出的影片", "").strip()

    # ── Video rows ────────────────────────────────────────────────────────────
    rows = soup.select("table.videotextlist tr")

    print(f"[TRACKER] parser: name={name!r}, rows={len(rows)}", flush=True)

    videos: list[dict] = []
    for row in rows:
        # Skip the header row
        if "header" in (row.get("class") or []):
            continue

        tds = row.select("td")
        if len(tds) < 2:
            continue

        # Column 0: title link — use a[href] to skip the toolbar icon <a> tags
        a_el = tds[0].select_one("a[href]")
        if not a_el:
            continue
        raw = a_el.get_text(strip=True)
        parts = raw.split(None, 1)
        if not parts:
            continue
        ref = parts[0].upper()
        title = parts[1] if len(parts) > 1 else ""
        detail_href = a_el.get("href", "")
        detail_url = urljoin(base_url, detail_href) if detail_href else ""

        # Column 1: release date
        date = tds[1].get_text(strip=True)

        videos.append({
            "ref": ref,
            "title": title,
            "date": date,
            "cover_url": "",        # text mode has no cover images
            "detail_url": detail_url,
            "seen": False,
        })

    print(f"[TRACKER] parser: parsed {len(videos)} videos", flush=True)
    return name, videos


def _detect_total_pages(soup: BeautifulSoup, current_page: int) -> int | None:
    """Extract page-count from JAVLibrary pager links on the current HTML."""
    page_numbers: set[int] = set()

    for anchor in soup.select('a[href*="page="]'):
        href = str(anchor.get("href", ""))
        match = re.search(r"[?&]page=(\d+)", href)
        if match:
            page_numbers.add(int(match.group(1)))

    return max(page_numbers) if page_numbers else None


async def _fetch_actress_page_snapshot(browser, actress_id: str, page_num: int) -> tuple[BeautifulSoup, list[dict], str]:
    """Load one actress text page and return the parsed soup, videos, and actress name."""
    page_url = f"{JAVLIBRARY_BASE}vl_star.php?list&mode=&s={actress_id}&page={page_num}"
    print(f"[TRACKER] fetching page {page_num}: {page_url}", flush=True)
    tab = await browser.get(page_url)
    soup = await _wait_for_actress_content(tab, browser, context=f"actress {actress_id} page {page_num}")
    name, videos = _parse_actress_text_page(soup, JAVLIBRARY_BASE)
    return soup, videos, name


async def _fetch_actress_total_pages_impl(url: str) -> dict:
    """Fetch JAVLibrary's own page count for an actress listing from page 1."""
    actress_id = _actress_id_from_url(url)
    if not actress_id:
        raise ValueError(f"Cannot extract actress ID (?s=) from URL: {url}")

    pool = await _ensure_browser_pool()
    actress_profile = await pool.get()
    try:
        browser = await uc.start(
            user_data_dir=actress_profile,
            headless=False,
            browser_args=[
                "--window-size=1280,800",
                "--window-position=-32000,-32000",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )
    except Exception:
        pool.put_nowait(actress_profile)
        raise
    try:
        soup, videos, name = await _fetch_actress_page_snapshot(browser, actress_id, 1)
        total_pages = _detect_total_pages(soup, 1)
        if total_pages is None and videos:
            total_pages = 1
        return {
            "name": name,
            "total_pages": total_pages,
        }
    finally:
        try:
            browser.stop()
        finally:
            pool.put_nowait(actress_profile)


async def _scrape_actress_page_impl(
    url: str,
    known_refs: set[str] | None = None,
    start_page: int = 1,
    end_page: int = 9999,
) -> dict:
    """
    Scrape a javlibrary actress listing in text mode, handling pagination.

    Pagination behaviour:
    - known_refs is None  → scrape ALL pages (first-ever add; builds full history).
    - known_refs provided → smart-stop: halt when an entire page's refs are already
      in known_refs, meaning we have caught up with what we previously stored.
    - start_page / end_page allow fetching a specific page range (for Load More).

    A 1.5-second courtesy delay is added between page navigations.

    Returns:
        {
            "name":          str,
            "videos":        list[dict],   # accumulated across all pages fetched
            "pages_scraped": int,
            "has_more":      bool,         # True = smart-stop triggered (more may exist)
            "next_page":     int | None,   # page number to resume from if has_more
            "total_pages":   int | None,   # page count reported by JAVLibrary pager
        }

    Raises ValueError if actress_id cannot be extracted.
    """
    actress_id = _actress_id_from_url(url)
    if not actress_id:
        raise ValueError(f"Cannot extract actress ID (?s=) from URL: {url}")

    def _page_url(page: int) -> str:
        return f"{JAVLIBRARY_BASE}vl_star.php?list&mode=&s={actress_id}&page={page}"

    pool = await _ensure_browser_pool()
    actress_profile = await pool.get()
    try:
        browser = await uc.start(
            user_data_dir=actress_profile,
            headless=False,
            browser_args=[
                "--window-size=1280,800",
                "--window-position=-32000,-32000",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )
    except Exception:
        pool.put_nowait(actress_profile)
        raise
    try:
        all_videos: list[dict] = []
        actress_name = ""
        pages_scraped = 0
        has_more = False
        next_page_out: int | None = None
        detected_total_pages: int | None = None
        last_page_had_videos = False  # tracks whether the final page in the loop had content

        for page_num in range(start_page, end_page + 1):
            soup, page_videos, name = await _fetch_actress_page_snapshot(browser, actress_id, page_num)
            page_total = _detect_total_pages(soup, page_num)
            if page_total is not None:
                detected_total_pages = max(detected_total_pages or 0, page_total)
            if name and not actress_name:
                actress_name = name
            pages_scraped += 1

            last_page_had_videos = bool(page_videos)

            if not page_videos:
                if page_num == start_page:
                    # Dump HTML for debugging so the user can inspect the actual structure
                    import tempfile, pathlib
                    dump_path = pathlib.Path(tempfile.gettempdir()) / "javlibrary_actress_debug.html"
                    dump_path.write_text(soup.prettify(), encoding="utf-8")
                    raise ValueError(
                        f"No videos found on actress page (page 1). "
                        f"The page loaded but no video rows could be parsed. "
                        f"Debug HTML saved to: {dump_path}"
                    )
                # Later page returned no rows = past the last page
                break

            all_videos.extend(page_videos)

            # Smart-stop: if every ref on this page is already known, we've caught up
            if known_refs is not None:
                page_refs = {v["ref"] for v in page_videos}
                if page_refs.issubset(known_refs):
                    has_more = True
                    next_page_out = page_num + 1
                    break

            # Courtesy delay before the next page navigation
            if page_num < end_page:
                await asyncio.sleep(_PAGE_DELAY)

        # If the loop ran to completion (hit end_page) and the last page
        # had videos, there may be more pages beyond — flag them for Load More.
        if not has_more and last_page_had_videos and pages_scraped == (end_page - start_page + 1):
            has_more = True
            next_page_out = end_page + 1

        # If the requested page range did not expose pager links, ask page 1 directly
        # because JAVLibrary usually exposes the full pager there.
        if detected_total_pages is None:
            if start_page != 1:
                soup1, videos1, name1 = await _fetch_actress_page_snapshot(browser, actress_id, 1)
                if name1 and not actress_name:
                    actress_name = name1
                detected_total_pages = _detect_total_pages(soup1, 1)
                # Page 1 with rows and no pager implies a single-page listing.
                if detected_total_pages is None and videos1:
                    detected_total_pages = 1
            elif detected_total_pages is None and all_videos:
                # Same single-page inference when we already fetched page 1.
                detected_total_pages = 1

        if detected_total_pages is not None:
            if end_page >= detected_total_pages:
                has_more = False
                next_page_out = None
            elif not has_more:
                has_more = True
                next_page_out = end_page + 1

        return {
            "name": actress_name,
            "videos": all_videos,
            "pages_scraped": pages_scraped,
            "has_more": has_more,
            "next_page": next_page_out,
            "total_pages": detected_total_pages,
        }

    finally:
        try:
            browser.stop()
        finally:
            pool.put_nowait(actress_profile)


async def search_javlibrary(keyword: str) -> Dict:
    keyword = keyword.strip().upper()
    retry_key = f"search:{keyword}"
    return await _handle_rate_limited_operation(
        retry_key,
        f"metadata {keyword}",
        lambda: _search_javlibrary_impl(keyword),
    )


async def fetch_actress_total_pages(url: str) -> dict:
    actress_id = _actress_id_from_url(url)
    if not actress_id:
        raise ValueError(f"Cannot extract actress ID (?s=) from URL: {url}")

    retry_key = f"actress-total-pages:{actress_id}"
    return await _handle_rate_limited_operation(
        retry_key,
        f"actress {actress_id} total pages",
        lambda: _fetch_actress_total_pages_impl(url),
    )


async def scrape_actress_page(
    url: str,
    known_refs: set[str] | None = None,
    start_page: int = 1,
    end_page: int = 9999,
) -> dict:
    actress_id = _actress_id_from_url(url)
    if not actress_id:
        raise ValueError(f"Cannot extract actress ID (?s=) from URL: {url}")

    retry_key = (
        f"actress-scrape:{actress_id}:{int(start_page)}:{int(end_page)}:"
        f"{_known_refs_fingerprint(known_refs)}"
    )
    return await _handle_rate_limited_operation(
        retry_key,
        f"actress {actress_id} scrape {start_page}-{end_page}",
        lambda: _scrape_actress_page_impl(
            url,
            known_refs=known_refs,
            start_page=start_page,
            end_page=end_page,
        ),
    )


async def scrape_actress_page_range(url: str, start_page: int, end_page: int) -> dict:
    """
    Scrape exactly pages start_page..end_page inclusive.
    Used by the tracker's "Load 1 More Page" and "Load All Remaining" buttons.
    No smart-stop — always fetches the requested range.
    """
    return await scrape_actress_page(
        url,
        known_refs=None,   # disable smart-stop; fetch the full range
        start_page=start_page,
        end_page=end_page,
    )
