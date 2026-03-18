# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) and other AI agents when working with code in this repository.

## Running the App

```bash
# First-time setup
setup.bat          # deletes and recreates venv, installs requirements.txt

# Start the app (http://localhost:8765)
run.bat            # activates venv, runs python main.py

# Or directly in the activated venv
python main.py

# Build a distributable installer (PyInstaller --onedir + Inno Setup)
build.bat
```

`build.bat` produces:
- `dist/JAV Downloader/` — raw distributable folder
- `setup/JAV Downloader Setup.exe` — installer (installs to `%LOCALAPPDATA%\Programs\JAV Downloader`)

## Architecture

**Stack:** NiceGUI (FastAPI under the hood) + Python 3.x, no database — state lives in `app.storage.user` (NiceGUI server-side session dict) and persistent JSON files in `DATA_DIR`.

**Data directory** (`utils/paths.py` → `DATA_DIR`): resolved at startup from:
1. `data_dir.txt` next to the executable (or `main.py`)
2. `%APPDATA%\JAV Downloader` (Windows default)
3. `~/.jav-downloader` (non-Windows fallback)

Contains: `config.json`, `.env`, `tracker.json`, `covers/`, NiceGUI storage.

### Module System

`main.py` (119 lines) is the minimal entry point. It imports page modules (which register their own `@ui.page` routes) and runs NiceGUI on port 8765.

```
main.py
├── organiser/page.py   → @ui.page("/organiser")
├── tracker/page.py     → @ui.page("/tracker")
├── downloader/page.py  → @ui.page("/downloader")
└── api/routes.py       → FastAPI endpoints
```

| Module | Route | Accent | Description |
|---|---|---|---|
| Launchpad | `/` | — | Entry point; 3-card grid |
| Downloader | `/downloader` | Indigo `#4f46e5` / `#6366f1` | Metadata scraping, LLM translation, qBittorrent queueing |
| Organiser | `/organiser` | Emerald `#059669` / `#10b981` | File renaming, actor-based folder sorting |
| Tracker | `/tracker` | Amber `#d97706` / `#f59e0b` | Actress release tracking |

All pages share `assets/theme.css` (global dark stylesheet, ~860 lines) and a 60px header with a home button.

### Downloader (`downloader/`)

- **`downloader/page.py`** (~1,800 lines) — main `/downloader` NiceGUI page
- **`downloader/state.py`** — session storage key helpers
- **`downloader/components/inspector.py`** (~914 lines) — right-panel inspector (lazy-attached on first selection)
- **`downloader/components/queue.py`** (~199 lines) — left sidebar queue entry builder & badge updater
- **`downloader/components/settings.py`** (~418 lines) — settings dialog builder

**UI Layout:** Header → two-pane workspace (left queue sidebar + right inspector)

**Handle dict** (`all_handles[keyword]`): carries UI element refs (`row_el`, `status_dot`, `badge_n/t/m/zh`, …) and runtime state (`state["_jav_result"]`, `state["_nyaa_result"]`, `state["folder_path"]`, `state["downloaded"]`).

**Key functions:**
- `_parse_keywords(raw)` — normalises input to uppercase ref list
- `_fetch_one(keyword)` — fetches metadata + torrents with scraper fallback
- `_attach_inspector(h, col)` — lazily builds inspector widgets on first selection
- `_build_youcom_url()` — generates You.com chat URL with JAV metadata

**Badge meanings on queue rows:** N (not downloaded), T (translated), M (metadata), 中 (Chinese title ready)

### Organiser (`organiser/`)

- **`organiser/page.py`** (~1,676 lines) — two-tab UI: Rename Files | Move to Actor

**Rename tab:** scans folder for `YYYYMMDD - Video Name Actor REF-123` pattern; previews and confirms batch renames.

**Move tab:** detects actor from video filenames; moves date-prefixed folders into actor subdirectories.

**API endpoints defined in this module:**
- `GET /api/organiser-img?path=<encoded>` — serves folder images
- `GET /api/organiser-open-folder?path=<encoded>` — opens folder in Explorer

### Tracker (`tracker/`)

- **`tracker/page.py`** (~1,121 lines) — two-panel UI (actress list + video inspector)
- **`tracker/store.py`** (~186 lines) — JSON persistence (`tracker.json`); CRUD for actresses, seen-state, ratings
- **`tracker/state.py`** (~45 lines) — ephemeral in-memory pagination state
- **`tracker/fetch_queue.py`** (~111 lines) — background cover-fetch scheduler

Scrapes JAVLibrary actress pages via `scraper/javlibrary.py`; supports pagination ("Load More"), star ratings (0.5–5.0), mark-seen, and auto-queueing new releases to the downloader.

### API (`api/routes.py`)

FastAPI endpoints with CORS enabled (all origins, for `chrome-extension://`):

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/queue` | Receive `{"refs": [...]}` from extension; returns `{"added": N, "skipped": M}` |
| `GET` | `/api/cover` | Serve cached cover image by `?ref=ABC-123` |
| `GET` | `/api/organiser-img` | Serve folder images for organiser |
| `GET` | `/api/organiser-open-folder` | Open folder in Explorer |

## Scrapers (`scraper/`)

| Module | Site | Method |
|---|---|---|
| `javdb.py` | javdb.com | `curl_cffi` Chrome TLS fingerprint; age gate via `over18=1` cookie; proxy rotation from `config.json → javdb_proxies`; runs sync in `asyncio.to_thread` |
| `javlibrary.py` | javlibrary.com | `nodriver` headless Chrome; Cloudflare auto-solved; `cf_clearance` persisted in `chrome_profile/` (inside DATA_DIR) |
| `nyaa.py` | sukebei.nyaa.si | Plain `requests` + BeautifulSoup |

Both JAV scrapers return: `{title, cover_url, id, date, studio, actresses, genres}`.

`javlibrary.py` also exports `scrape_actress_page()` / `scrape_actress_page_range()` used by the Tracker.

**Rate limiting** (`utils/scraper_lock.py`): `SCRAPER_SEM = _ScraperLock(cooldown=2.0)` — serial requests with a mandatory 2-second cooldown between releases. Shared by all metadata fetches and cover downloads.

`JAVLIBRARY_BROWSER_SEM = asyncio.Semaphore(1)` — prevents two browser windows from competing.

## Translation (`translator/llm.py`)

- OpenAI-compatible API; `provider/model/base_url` in `config.json`, API keys in `.env`.
- `translate_title(title, date, actresses, ref_id, config)` → raw LLM response string.
- `extract_code_blocks(response)` → extracts candidate titles from fenced code blocks.
- **Output format:** `YYYYMMDD - 標題 女優A、女優B 番號`
- Actresses joined with `、` (fullwidth comma). Spaces between names are forbidden.

**Configured providers:** Kilo Code, Kimi K2, Z.ai, Z.ai Coding, Opencode Zen, Custom.

## Utilities (`utils/`)

| Module | Key exports |
|---|---|
| `paths.py` | `DATA_DIR`, `CONFIG_FILE`, `ENV_FILE`, `CHROME_PROFILE_DIR`, `COVERS_DIR`, `TRACKER_FILE`, `set_data_dir()`, `reload_paths()` |
| `covers.py` | `cover_path(ref)`, `cover_exists(ref)`, `save_cover_bytes()`, `fetch_and_cache_cover()` |
| `folder.py` | `create_video_folder()`, `download_cover()` |
| `qbittorrent.py` | `add_torrent()`, `get_torrents()`, `get_all_torrents()`, `is_reachable()` |
| `organiser.py` | `FolderInfo`, `MoverInfo`, `load_renamer_folders()`, `rename_folders_batch()`, `load_mover_folders()`, `move_folders_batch()`, `generate_thumbnails()` |
| `scraper_lock.py` | `SCRAPER_SEM` (shared rate-limit lock) |
| `sort_key.py` | `romaji_key(text)`, `log_sorted_order(label, items, name_fn)` — multilingual sort |
| `cjk_strokes.bin` | 20KB binary stroke-count lookup for CJK U+4E00–U+9FFF |

### Multilingual Sorting (`utils/sort_key.py`)

All three modules (Tracker, Organiser, Downloader) import `romaji_key` from this shared utility for A-Z sorting of actress/actor names that mix English, Japanese, and Chinese.

**Three independent buckets, in this order:**

| Bucket | Characters | Sort method |
|---|---|---|
| 0 — Latin | Has any ASCII letter `[a-zA-Z]` | Alphabetical via pykakasi passthrough |
| 1 — Japanese | Has hiragana, katakana, or `々〆〇` (U+3005–7) | Romaji A-Z via pykakasi |
| 2 — Chinese | Pure CJK, no kana, no Latin | Stroke count ascending; same-stroke tied by Unicode codepoint |
| ∞ — Blank | Empty or `—` | Always last (`\uffff`) |

**Bucket 2 key formula** — per CJK character: `f'{stroke_count:03d}{codepoint:06d}'`
- Primary: stroke count (fewer strokes first)
- Tiebreaker: Unicode codepoint — identical characters always cluster as a subgroup (e.g. all 三× names are adjacent, all 小× names are adjacent)

**Stroke data:** `utils/cjk_strokes.bin` — flat bytes array from Unicode Unihan `kTotalStrokes`, index = `codepoint − 0x4E00`, value = stroke count. 0 = unknown → sorts to end of Chinese bucket.

**Performance:** Binary file loads in ~43ms; pykakasi lazy-initialised on first use (~355ms once); results LRU-cached (`maxsize=4096`) so repeated sorts are instant.

**`SORT_DEBUG = True`** (top of `sort_key.py`) — logs each name's bucket and key to stderr, plus a final sorted-order summary via `log_sorted_order()`. Set `False` to silence.

## Configuration

**`config.json`** (stored in `DATA_DIR`):

```
provider, base_url, model         # LLM
download_folder, qbt_url,
  qbt_username                    # qBittorrent
metadata_source                   # "javdb" | "javlibrary"
dl_poll_interval                  # int, seconds (default 30)
dl_cover_fields                   # list of UI fields to show
vtm_exe, vtm_preset               # Video Thumbnails Maker
losslesscut_exe                   # LosslessCut path
trans_concurrency                 # int, parallel translation jobs (default 3)
javdb_proxies                     # list of proxy URLs for javdb
tracker_cover_w                   # int, tracker cover width px
organiser_scan_folder             # default scan directory
organiser_mover_base              # default mover target directory
```

**`.env`** (stored in `DATA_DIR`): `KILO_CODE_API_KEY`, `KIMI_K2_API_KEY`, `ZAI_API_KEY`, `OPENCODE_ZEN_API_KEY`, `CUSTOM_API_KEY`, `QBT_PASSWORD`.

## Browser Extension (`extension/`)

Chrome Manifest V3. Scans all open tabs for JAV refs (`/\b([A-Z]{2,7}-\d{2,5})\b/g`). Three-step popup: select refs → confirm/edit → send. POSTs to `http://localhost:8765/api/queue`.

## JAV Folder Naming Protocol

Used by both Downloader (creating folders) and Organiser (renaming):

- **Input folder name:** `YYYYMMDD - Video Name Actor REF-123`
- **After rename:**
  - Folder → `YYYYMMDD - Video Name`
  - Videos → `Actor - Video Name[- N].ext`
  - WebP files → `REF Thumbnails[N].webp`
  - Large JPG (>700 KB) → `REF Thumbnails[N].jpg`
  - Small JPG (≤700 KB) → `REF Cover[N].jpg`

## Key Conventions

- **Ref numbers are always uppercase** — `_parse_keywords()` normalises input.
- **Metadata source fallback** — if primary source fails, `_fetch_one()` retries with the other.
- **Shared ref lifecycle is reference-based across modules** — cover files and cached metadata for a ref must persist as long as either Tracker or Downloader still references that ref. Only prune shared cache/assets after the final reference disappears from both modules.
- **`chrome_profile/`** inside `DATA_DIR` — nodriver's persistent Chrome profile. Do not delete; holds `cf_clearance` cookie.
- **NiceGUI storage** — explicitly set to `DATA_DIR / "storage"` to avoid SMB network drive async write stalls.
- **No test suite** — verify by running the app.
- **Pending refactor** — `SETTINGS_REFACTOR_PLAN.md` documents a planned unified tabbed settings dialog across all modules.
