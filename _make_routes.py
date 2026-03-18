from pathlib import Path

root = Path(r"c:\Users\KeySteps\Downloads\Video Downloader JAV")
src = (root / "main.py").read_text(encoding="utf-8")

header = '''\
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


'''

# Extract: CORSMiddleware block + _JAV_RE_API + api_cover + api_queue
# Anchor: from "# ── Browser-extension API endpoint" to "\nui.run("
b_start = src.index("# ── Browser-extension API endpoint")
b_end   = src.index("\nui.run(")
api_block = src[b_start:b_end].rstrip()

# Remove the _ext_ref_queue definition (it now lives in downloader/page.py and is imported above)
api_block = api_block.replace(
    "# Thread-safe queue: extension POST drops refs here; build_ui timer drains it\n"
    "_ext_ref_queue: _queue_mod.Queue = _queue_mod.Queue()\n",
    "",
)

content = header + api_block + "\n"

(root / "api" / "routes.py").write_text(content, encoding="utf-8")
print(f"Written api/routes.py — {len(content.splitlines())} lines")
