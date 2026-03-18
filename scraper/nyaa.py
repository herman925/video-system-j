"""
Scraper for sukebei.nyaa.si torrent search results.
Uses plain requests + BeautifulSoup (no Cloudflare on this site).
"""
import requests
from bs4 import BeautifulSoup
from typing import List, Dict

NYAA_SEARCH_URL = "https://sukebei.nyaa.si/?f=0&c=0_0&q={}"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def search_nyaa(keyword: str) -> List[Dict]:
    """
    Search sukebei.nyaa.si for torrents matching *keyword*.

    Returns a list of dicts (sorted by seeders desc):
        name, size, date, seeders, leechers, downloads, magnet, torrent
    Raises requests.HTTPError on non-200 responses.
    """
    url = NYAA_SEARCH_URL.format(keyword)
    resp = requests.get(url, headers=_HEADERS, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    results: List[Dict] = []

    for row in soup.select("table.torrent-list tbody tr"):
        cols = row.find_all("td")
        if len(cols) < 8:
            continue

        # ── Name (column 1) ───────────────────────────────────────────────────
        # The name link goes to /view/<id>, not to #comments
        name = ""
        for a in cols[1].find_all("a", href=True):
            href = a["href"]
            if "/view/" in href and "#" not in href:
                name = a.get_text(strip=True)
                break
        if not name:
            # fallback: last anchor in the cell
            anchors = cols[1].find_all("a")
            if anchors:
                name = anchors[-1].get_text(strip=True)

        # ── Links (column 2) ──────────────────────────────────────────────────
        magnet_link = ""
        torrent_link = ""
        for a in cols[2].find_all("a", href=True):
            href = a["href"]
            if href.startswith("magnet:"):
                magnet_link = href
            elif href.endswith(".torrent") or "/download/" in href:
                if not href.startswith("http"):
                    href = "https://sukebei.nyaa.si" + href
                torrent_link = href

        # ── Numeric fields ────────────────────────────────────────────────────
        def _int(text: str) -> int:
            t = text.strip()
            return int(t) if t.isdigit() else 0

        size      = cols[3].get_text(strip=True)
        date      = cols[4].get_text(strip=True)
        seeders   = _int(cols[5].get_text())
        leechers  = _int(cols[6].get_text())
        downloads = _int(cols[7].get_text())

        if name and (magnet_link or torrent_link):
            results.append(
                {
                    "name":      name,
                    "size":      size,
                    "date":      date,
                    "seeders":   seeders,
                    "leechers":  leechers,
                    "downloads": downloads,
                    "magnet":    magnet_link,
                    "torrent":   torrent_link,
                }
            )

    results.sort(key=lambda x: x["seeders"], reverse=True)
    return results
