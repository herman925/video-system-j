"""
Session persistence helpers shared between all downloader components.
"""

from utils.downloader_store import save_downloader_queue_cache
from utils.save_state import tracked_save_state


_SESSION_KEY = "jav_dl_queue"
_CACHE_KEY = "jav_dl_cache"  # kw -> {jav: {...}, nyaa: [...]}


def _session_save(all_handles: dict) -> None:
    """Persist queue list + full metadata cache to the stable downloader store."""
    with tracked_save_state("downloader"):
        items = []
        cache = {}  # build clean — never read-and-augment, so deleted items can't linger
        for kw, h in all_handles.items():
            st = h["state"]
            jav = st.get("_jav_result") or {}
            fp = st.get("folder_path")
            items.append(
                {
                    "kw": kw,
                    "title": jav.get("title", ""),
                    "folder_path": str(fp) if fp else "",
                    "downloaded": bool(st.get("downloaded")),
                    "ever_selected": bool(st.get("_ever_selected")),
                }
            )
            if h["state"].get("_populated"):
                jav_r = h["state"].get("_jav_result")
                nyaa_r = h["state"].get("_nyaa_result")
                name_sel = h.get("name_sel")
                cache[kw] = {
                    "jav": jav_r if isinstance(jav_r, dict) else None,
                    "nyaa": nyaa_r if isinstance(nyaa_r, list) else [],
                    "translation": h["state"].get("_translation") or "",
                    "name_choices": h["state"].get("_name_choices") or [],
                    "selected_name": (name_sel.value if name_sel else None) or "",
                }
        save_downloader_queue_cache(items, cache)
