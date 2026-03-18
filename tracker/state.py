"""
Ephemeral per-actress page-fetch state.
Lives in memory only, but mirrors fields persisted in tracker.json.

pages_loaded  — historical compatibility field; highest contiguous pages count
                known from older tracker sessions.
next_page     — smallest known page not yet fetched, if determinable.
has_more      — True while there are known or suspected unfetched pages.
total_pages   — detected page count when the scraper could infer one.
fetched_pages — explicit list of fetched/refetched page numbers.
"""

_pagination: dict[str, dict] = {}


def set_pagination(
    actress_id: str,
    *,
    has_more: bool,
    next_page: int | None,
    pages_scraped: int,
    pages_loaded: int | None = None,
    total_pages: int | None = None,
    fetched_pages: list[int] | None = None,
) -> None:
    existing = _pagination.get(actress_id, {})
    _pagination[actress_id] = {
        "has_more": has_more,
        "next_page": next_page,
        "pages_scraped": pages_scraped,
        # pages_loaded is passed explicitly by callers that change it (first add,
        # load-more); refresh passes None to preserve the existing value.
        "pages_loaded": pages_loaded if pages_loaded is not None
                        else existing.get("pages_loaded", pages_scraped),
        "total_pages": total_pages if total_pages is not None else existing.get("total_pages"),
        "fetched_pages": sorted(
            {
                max(1, int(page))
                for page in (fetched_pages if fetched_pages is not None else existing.get("fetched_pages", []))
                if str(page).strip()
            }
        ),
    }


def get_pagination(actress_id: str) -> dict:
    return _pagination.get(
        actress_id,
        {
            "has_more": False,
            "next_page": None,
            "pages_scraped": 0,
            "pages_loaded": 0,
            "total_pages": None,
            "fetched_pages": [],
        },
    )


def clear_pagination(actress_id: str) -> None:
    _pagination.pop(actress_id, None)
