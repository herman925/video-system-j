"""
Scraper for javdb.com.

Uses curl_cffi for a realistic browser TLS fingerprint.
No Cloudflare on this site — runs fully headless/silent.

Age-gate: javdb shows an 18+ confirmation modal on first visit.
We bypass it by pre-setting the confirmation cookie in the session and
by visiting the home page once to let the server record the cookie before
hitting the search endpoint.

Ref numbers MUST be ALL-CAPS (javdb is case-sensitive).
Search results are fuzzy, so we filter for an exact ID match.
"""
import asyncio
import json
from pathlib import Path
from typing import Dict, List, Optional

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

JAVDB_BASE   = "https://javdb.com"
JAVDB_SEARCH = JAVDB_BASE + "/search?q={}&f=all"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection":      "keep-alive",
}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _load_proxies() -> List[str]:
    """Read the javdb_proxies list from config.json (one entry per line)."""
    try:
        from utils.paths import CONFIG_FILE
        if CONFIG_FILE.exists():
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            proxies = cfg.get("javdb_proxies", [])
            if isinstance(proxies, list):
                return [p.strip() for p in proxies if isinstance(p, str) and p.strip()]
    except Exception:
        pass
    return []


def _proxy_dict(proxy_url: str) -> dict:
    """Turn a proxy URL string into a curl_cffi-compatible proxies dict."""
    return {"http": proxy_url, "https": proxy_url}


def _get(
    session: cffi_requests.Session,
    url: str,
    proxy: Optional[str] = None,
) -> BeautifulSoup:
    kwargs = {"headers": _HEADERS, "timeout": 20}
    if proxy:
        kwargs["proxies"] = _proxy_dict(proxy)
    resp = session.get(url, **kwargs)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def _confirm_age(session: cffi_requests.Session, proxy: Optional[str] = None) -> None:
    """
    Visit the home page with the over18 cookie already set so the server
    registers the confirmation before we hit the search endpoint.
    The modal is cookie-gated — setting the cookie is enough to bypass it.
    """
    session.cookies.set("over18", "1", domain="javdb.com")
    try:
        kwargs = {"headers": _HEADERS, "timeout": 10}
        if proxy:
            kwargs["proxies"] = _proxy_dict(proxy)
        session.get(JAVDB_BASE, **kwargs)
    except Exception:
        pass  # home page is just a warm-up; errors here are non-fatal


def _parse_detail(soup: BeautifulSoup) -> Dict:
    """Extract the same metadata fields as search_javlibrary()."""
    result: Dict = {}

    # ── Title ─────────────────────────────────────────────────────────────────
    # javdb renders:
    #   <h2 class="title is-4">
    #     <strong>SNOS-079</strong>          ← ref ID, NOT the title
    #     <strong class="current-title">actual title text</strong>
    #   </h2>
    for sel in (
        "h2.title strong.current-title",
        ".title.is-4 strong.current-title",
        "h2.title strong:nth-of-type(2)",
    ):
        el = soup.select_one(sel)
        if el:
            result["title"] = el.get_text(strip=True)
            break
    # fallback: second <strong> inside the h2
    if not result.get("title"):
        strongs = soup.select("h2.title strong")
        if len(strongs) >= 2:
            result["title"] = strongs[1].get_text(strip=True)
        elif len(strongs) == 1:
            result["title"] = strongs[0].get_text(strip=True)

    # ── Cover image ───────────────────────────────────────────────────────────
    # Use img.video-cover directly — ".video-cover img" grabs the play-button SVG child instead
    for sel in (
        "img.video-cover",
        ".column-video-cover img.video-cover",
        ".video-detail img.video-cover",
        ".cover-container img",
    ):
        el = soup.select_one(sel)
        if el:
            src = el.get("src") or el.get("data-src") or el.get("data-original", "")
            if src.startswith("//"):
                src = "https:" + src
            if src:
                result["cover_url"] = src
            break

    # ── Metadata panel rows ───────────────────────────────────────────────────
    # javdb detail page uses <nav class="panel"> with <div class="panel-block">
    # Each row: <strong>Label:</strong> <span>value</span> or <a>value</a>
    panel_rows = soup.select(
        ".video-meta-panel .panel-block, "
        ".movie-panel-info .panel-block, "
        "nav.panel .panel-block"
    )
    for row in panel_rows:
        strong = row.select_one("strong")
        if not strong:
            continue
        label = strong.get_text(strip=True).rstrip(":：").strip()

        # Collect text values from spans and links in this row
        value_els = row.select("span:not(.tag), a")
        values    = [e.get_text(strip=True) for e in value_els if e.get_text(strip=True)]

        label_lower = label.lower()

        if any(k in label_lower for k in ("番號", "id", "編號")):
            if values:
                result.setdefault("id", values[0])

        elif any(k in label_lower for k in ("日期", "發行", "date", "release")):
            if values:
                result.setdefault("date", values[0])

        elif any(k in label_lower for k in ("片商", "製作", "發行商", "maker", "studio", "label")):
            if values:
                result.setdefault("studio", values[0])

        elif any(k in label_lower for k in ("演員", "actress", "cast", "出演")):
            # javdb marks gender with a sibling <strong class="symbol female">♀</strong>
            # or <strong class="symbol male">♂</strong> immediately after each <a>.
            # We collect only the female (♀) ones; if no gender marks exist, take all.
            actresses = []
            male_only = []
            actor_links = row.select("a")
            for a_el in actor_links:
                name = a_el.get_text(strip=True)
                if not name:
                    continue
                # Look for the very next sibling strong.symbol
                gender_mark = a_el.find_next_sibling("strong", class_="symbol")
                if gender_mark and "♀" in gender_mark.get_text():
                    actresses.append(name)
                elif gender_mark and "♂" in gender_mark.get_text():
                    male_only.append(name)
                else:
                    actresses.append(name)  # no gender tag → keep
            result["actresses"] = actresses if actresses else male_only

        elif any(k in label_lower for k in ("類別", "tags", "genre", "tag", "類型")):
            result["genres"] = [
                a.get_text(strip=True)
                for a in row.select("a")
                if a.get_text(strip=True)
            ]

    return result


# ── Public API ────────────────────────────────────────────────────────────────

def search_javdb(keyword: str) -> Dict:
    """
    Search javdb.com for *keyword* (e.g. "WAAA-622").

    * keyword is forced to uppercase — javdb is case-sensitive.
    * The 18+ age gate is bypassed by cookie injection.
    * Fuzzy search results are filtered for an exact ID match.

    Returns a metadata dict with the same shape as search_javlibrary():
        title, cover_url, id, date, studio, actresses, genres

    Raises ValueError  if no exact match is found.
    Raises HTTPError   on non-200 responses.
    """
    keyword = keyword.strip().upper()

    # Build proxy rotation list: [None] = direct, then each configured proxy
    proxies = _load_proxies()
    # Always try direct first (None = no proxy), then fall back to proxies
    rotation = [None] + proxies
    last_exc: Exception = ValueError("Unknown error")

    for attempt, proxy in enumerate(rotation):
        if proxy:
            print(f"[javdb] Attempt {attempt + 1}: using proxy {proxy}", flush=True)
        try:
            result = _search_javdb_with_proxy(keyword, proxy)
            return result
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            last_exc = exc
            if status in (403, 429, 503) or "ip" in str(exc).lower() or "blocked" in str(exc).lower():
                print(f"[javdb] {'Direct' if not proxy else proxy} blocked (HTTP {status}), "
                      f"{'trying next proxy' if attempt < len(rotation) - 1 else 'all proxies exhausted'}",
                      flush=True)
                continue
            # Non-ban errors (e.g. no results found) – don't rotate, just raise
            raise

    raise last_exc


def _search_javdb_with_proxy(keyword: str, proxy: Optional[str]) -> Dict:
    """Inner search implementation using a specific proxy (or None for direct)."""
    with cffi_requests.Session(impersonate="chrome124") as session:

        # ── Bypass age gate ───────────────────────────────────────────────────
        _confirm_age(session, proxy)

        # ── Search ────────────────────────────────────────────────────────────
        search_soup = _get(session, JAVDB_SEARCH.format(keyword), proxy)

        # ── Find exact match in result cards ─────────────────────────────────
        # Each result card has a UID badge (the ref number) we can compare.
        items = search_soup.select(
            ".movie-list .item, "
            ".search-result-items .item, "
            ".video-list .item"
        )
        if not items:
            raise ValueError(f"No results found for '{keyword}' on javdb.com")

        detail_url: str | None = None
        for item in items:
            # The ID badge selector — javdb commonly uses .uid or a <strong> inside .video-title
            uid_el = (
                item.select_one(".uid")
                or item.select_one(".video-title strong")
                or item.select_one("strong.video-title")
            )
            if uid_el and uid_el.get_text(strip=True).upper() == keyword:
                a = item.select_one("a[href]")
                if a:
                    href = a["href"]
                    detail_url = (
                        JAVDB_BASE + href if href.startswith("/") else href
                    )
                    break

        if not detail_url:
            raise ValueError(
                f"'{keyword}' was not found among javdb.com search results "
                f"({len(items)} fuzzy result(s) returned, none matched exactly). "
                f"Try javlibrary.com as source instead."
            )

        # ── Scrape detail page ────────────────────────────────────────────────
        detail_soup = _get(session, detail_url, proxy)
        result = _parse_detail(detail_soup)

        # ── Save cover to shared file cache ───────────────────────────────────
        cover_url = result.get("cover_url", "")
        if cover_url:
            try:
                from utils.covers import save_cover_bytes
                print(f"[COVER][javdb] Downloading cover for {keyword} …", flush=True)
                cover_kwargs = {
                    "headers": {**_HEADERS, "Referer": JAVDB_BASE},
                    "timeout": 15,
                }
                if proxy:
                    cover_kwargs["proxies"] = _proxy_dict(proxy)
                r = session.get(cover_url, **cover_kwargs)
                if r.ok:
                    ext = Path(cover_url.split("?")[0]).suffix or ".jpg"
                    save_cover_bytes(keyword, r.content, ext)
                    print(f"[COVER][javdb] ✓ {keyword} Cover{ext} ({len(r.content):,} bytes)", flush=True)
                else:
                    print(f"[COVER][javdb] ✗ HTTP {r.status_code} for {keyword}", flush=True)
            except Exception as _e:
                print(f"[COVER][javdb] ✗ {keyword}: {_e}", flush=True)

        return result


# ── Parallel racing API ───────────────────────────────────────────────────────

_JAVDB_POOL_OBJ: "_JavdbPoolState | None" = None
_JAVDB_SEM:      "asyncio.Semaphore | None" = None


class _JavdbPoolState:
    """
    Tracks per-connection health for one fetch session.

    Round-robin assignment distributes keywords across connections fairly.
    A connection is **retired** after MAX_CONSEC_BANS consecutive ban errors
    (HTTP 403 / 429 / 503 or IP-block signals) and will never be assigned
    another keyword until reset_javdb_pool() is called.
    """
    MAX_CONSEC_BANS = 3

    def __init__(self, connections: list) -> None:
        self._connections = list(connections)
        self._consec_bans: dict = {c: 0 for c in connections}
        self._lock = asyncio.Lock()
        self._rr = 0  # round-robin counter

    def _healthy(self) -> list:
        return [
            c for c in self._connections
            if self._consec_bans.get(c, 0) < self.MAX_CONSEC_BANS
        ]

    async def pick(self) -> "str | None":
        """Return the next healthy connection via round-robin, or None if all retired."""
        async with self._lock:
            healthy = self._healthy()
            if not healthy:
                return None
            conn = healthy[self._rr % len(healthy)]
            self._rr += 1
            return conn

    async def report_success(self, conn) -> None:
        async with self._lock:
            self._consec_bans[conn] = 0  # reset streak on any success

    async def report_ban(self, conn) -> None:
        async with self._lock:
            n = self._consec_bans.get(conn, 0) + 1
            self._consec_bans[conn] = n
            if n >= self.MAX_CONSEC_BANS:
                label = "direct" if conn is None else conn
                print(
                    f"[javdb] {label} retired after {self.MAX_CONSEC_BANS} "
                    f"consecutive ban errors — excluded for this session",
                    flush=True,
                )

    def any_healthy(self) -> bool:
        return bool(self._healthy())


def reset_javdb_pool() -> None:
    """Reset pool and semaphore so they re-initialise from config on next use."""
    global _JAVDB_POOL_OBJ, _JAVDB_SEM
    _JAVDB_POOL_OBJ = None
    _JAVDB_SEM = None


async def _get_javdb_resources() -> "tuple[asyncio.Semaphore, _JavdbPoolState]":
    global _JAVDB_POOL_OBJ, _JAVDB_SEM
    if _JAVDB_SEM is None or _JAVDB_POOL_OBJ is None:
        try:
            from translator.llm import load_config
            cfg = load_config()
            n = max(1, int(cfg.get("javdb_concurrency", 1)))
        except Exception:
            n = 1
        proxies = _load_proxies()
        connections = ([None] + proxies)[:n]   # slot-0 = direct, rest = proxies
        _JAVDB_SEM = asyncio.Semaphore(n)
        _JAVDB_POOL_OBJ = _JavdbPoolState(connections)
    return _JAVDB_SEM, _JAVDB_POOL_OBJ


def _is_ban_error(exc: Exception) -> bool:
    status = getattr(getattr(exc, "response", None), "status_code", None)
    return (
        status in (403, 429, 503)
        or "ip" in str(exc).lower()
        or "blocked" in str(exc).lower()
    )


async def search_javdb_racing(keyword: str) -> Dict:
    """
    Fetch JAVDB metadata using a fair connection pool with circuit breaking.

    Reads *javdb_concurrency* and *javdb_proxies* from config.json:

    Pool/queue model (NOT racing):
    - N concurrent keyword fetches run simultaneously, each using a different
      connection assigned via round-robin (direct, proxy1, proxy2, …).
    - If a connection returns a ban error (403/429/503), the job is handed to
      the **next healthy connection** automatically — the keyword is not lost.
    - After MAX_CONSEC_BANS (3) consecutive ban errors on one connection, that
      connection is **retired** for the session: no further keywords are
      assigned to it and it is never retried for this keyword either.
    - If all connections are retired, the function raises with a clear message.

    The module-level semaphore caps total concurrent JAVDB requests at N so
    the downloader and tracker together never exceed that limit.

    concurrency=1 (default): single serial path, identical to search_javdb().
    """
    sem, pool = await _get_javdb_resources()

    async with sem:
        if not pool.any_healthy():
            raise ValueError(
                f"All JAVDB connections are currently blocked (retired). "
                f"Add more proxies or restart the app to reset the session."
            )

        # Fast path: single connection
        if len(pool._connections) == 1:
            return await asyncio.to_thread(search_javdb, keyword)

        tried: set = set()
        last_exc: Exception = ValueError("No healthy connections available")

        while True:
            conn = await pool.pick()

            # conn is None when all connections are retired, or we've cycled
            # through every healthy connection already without success
            if conn is None or conn in tried:
                raise ValueError(
                    f"All configured JAVDB connections returned ban/block errors "
                    f"for '{keyword}'. "
                    f"({len(tried)} tried, none succeeded)"
                ) from last_exc

            tried.add(conn)
            label = "direct" if conn is None else conn
            print(f"[javdb] {label} → {keyword}", flush=True)

            try:
                result = await asyncio.to_thread(_search_javdb_with_proxy, keyword, conn)
                await pool.report_success(conn)
                return result

            except Exception as exc:
                if _is_ban_error(exc):
                    await pool.report_ban(conn)
                    last_exc = exc
                    remaining = pool.any_healthy()
                    print(
                        f"[javdb] {label} blocked for '{keyword}' — "
                        f"{'assigning to next healthy connection' if remaining else 'no connections left'}",
                        flush=True,
                    )
                    # Loop: pick() will return the next healthy, un-tried connection
                    continue

                # Non-ban error (e.g. no search results) — don't redistribute
                raise
