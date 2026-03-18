"""FastAPI endpoints for the browser extension API.

Registers /api/cover and /api/queue on the NiceGUI app.
Importing this module is sufficient to register the routes.
"""

import re
import queue as _queue_mod

from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from nicegui import app

from downloader.page import _ext_ref_queue


# ── Browser-extension API endpoint ────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # extension origin is chrome-extension://...
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type"],
)


_JAV_RE_API = re.compile(r"^[A-Z]{2,7}-\d{2,5}$")


@app.get("/api/cover")
async def api_cover(ref: str = "", _t: str = ""):
    """Serve a cached cover image from the shared COVERS_DIR by ref.

    _t is an ignored cache-buster parameter — it exists purely so the
    browser treats URLs with different ?_t= values as distinct requests
    after a cover is force-refreshed via deep-fetch.
    """
    if ref:
        from utils.covers import cover_path
        p = cover_path(ref)
        if p is not None:
            return FileResponse(
                str(p),
                headers={"Cache-Control": "public, max-age=31536000, immutable"},
            )
    return JSONResponse({"error": "not found"}, status_code=404)


@app.post("/api/queue")
async def api_queue(request: Request):
    """Receive JAV refs from the browser extension and add to queue."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "bad JSON"}, status_code=400)

    raw_refs = body.get("refs", [])
    if not isinstance(raw_refs, list):
        return JSONResponse({"error": "refs must be a list"}, status_code=400)

    refs = [
        r.strip().upper()
        for r in raw_refs
        if isinstance(r, str) and _JAV_RE_API.match(r.strip().upper())
    ]

    for ref in refs:
        _ext_ref_queue.put(ref)

    # Keep tracker seen-state in sync when refs arrive from the extension or API
    try:
        from tracker.store import mark_ref_seen_globally
        for ref in refs:
            mark_ref_seen_globally(ref)
    except Exception:
        pass  # tracker is optional; never break the queue endpoint

    return JSONResponse({"added": len(refs), "skipped": len(raw_refs) - len(refs)})
