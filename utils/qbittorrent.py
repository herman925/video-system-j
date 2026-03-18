"""
Minimal async qBittorrent Web API client.
Requires qBittorrent Web UI to be enabled (Tools → Preferences → Web UI).
"""
import httpx
from typing import Optional


async def add_torrent(
    url: str,
    save_path: str,
    qbt_url: str      = "http://localhost:8080",
    username: str     = "admin",
    password: str     = "adminadmin",
    rename: Optional[str] = None,
) -> bool:
    """
    Add a magnet link or .torrent URL to qBittorrent with a specific save path.
    Returns True on success, False on any error (including auth failure).
    """
    try:
        async with httpx.AsyncClient() as client:
            # ── Login ──────────────────────────────────────────────────────────
            login = await client.post(
                f"{qbt_url}/api/v2/auth/login",
                data={"username": username, "password": password},
                timeout=10,
            )
            if "Ok." not in login.text:
                return False

            # ── Add torrent ────────────────────────────────────────────────────
            data: dict = {
                "urls":          url,
                "savepath":      save_path,
                "autoTMM":       "false",
                "contentLayout": "NoSubfolder",  # place files directly in savepath
            }
            if rename:
                data["rename"] = rename

            resp = await client.post(
                f"{qbt_url}/api/v2/torrents/add",
                data=data,
                cookies=login.cookies,
                timeout=10,
            )
            return "Ok." in resp.text or resp.status_code == 200

    except Exception:
        return False


async def is_reachable(qbt_url: str = "http://localhost:8080") -> bool:
    """Quick check — returns True if qBittorrent Web UI responds."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{qbt_url}/api/v2/app/version", timeout=3)
            return r.status_code == 200
    except Exception:
        return False


async def get_torrents(
    qbt_url:  str = "http://localhost:8080",
    username: str = "admin",
    password: str = "adminadmin",
    save_path: Optional[str] = None,
    keyword:   Optional[str] = None,
) -> list:
    """
    Return torrent list from qBittorrent, optionally filtered.

    save_path — match exactly by save_path (case-insensitive, normalised separators).
    keyword   — match any torrent whose name contains the keyword (case-insensitive).
    Returns [] on any error.
    """
    try:
        async with httpx.AsyncClient() as client:
            login = await client.post(
                f"{qbt_url}/api/v2/auth/login",
                data={"username": username, "password": password},
                timeout=10,
            )
            if "Ok." not in login.text:
                return []

            resp = await client.get(
                f"{qbt_url}/api/v2/torrents/info",
                cookies=login.cookies,
                timeout=10,
            )
            if resp.status_code != 200:
                return []

            torrents: list = resp.json()

            if save_path:
                norm = save_path.replace("\\", "/").rstrip("/").lower()
                torrents = [
                    t for t in torrents
                    if t.get("save_path", "").replace("\\", "/").rstrip("/").lower() == norm
                ]
            elif keyword:
                kw = keyword.lower()
                torrents = [
                    t for t in torrents
                    if kw in t.get("name", "").lower()
                ]

            return torrents
    except Exception:
        return []


async def get_all_torrents(
    qbt_url:  str = "http://localhost:8080",
    username: str = "admin",
    password: str = "adminadmin",
) -> list:
    """
    Fetch every torrent from qBittorrent in a single API call.
    Used by the background poller to avoid N separate requests.
    Returns [] on any error.
    """
    return await get_torrents(qbt_url=qbt_url, username=username, password=password)
