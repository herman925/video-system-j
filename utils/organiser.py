"""
Organiser utilities: folder parsing, file renaming, folder moving,
VTM thumbnail generation, image listing, and external tool launching.

Ported from Video Organiser/Main.py and adapted for JAV Video System.
"""

import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

ScanProgressCallback = Callable[[dict], None]


def _emit_scan_progress(
    callback: Optional[ScanProgressCallback],
    *,
    kind: str,
    phase: str,
    scanned: int,
    total: int,
    discovered: int,
    force: bool = False,
) -> None:
    if callback is None:
        return
    if not force and scanned not in {0, total} and scanned > 3 and scanned % 10 != 0:
        return
    callback({
        'kind': kind,
        'phase': phase,
        'scanned': scanned,
        'total': total,
        'discovered': discovered,
    })

# ── Patterns ───────────────────────────────────────────────────────────────────

# Strict renamer: YYYYMMDD - Video Name Actor REF-123
RENAMER_RE = re.compile(r'^([0-9]{8})\s+-\s+(.*?)\s+(\S+)\s+([A-Za-z]+-[0-9]+)$')
# Loose mover detection: folder starts with a date prefix
MOVER_RE = re.compile(r'^\d{8}\s+-')
# Actor/video from video filename: Actor Name - Video Name [- index]
ACTOR_VIDEO_RE = re.compile(r'^(?P<Actor>[^-]+?)\s+-\s+(?P<Video>.+?)(?:\s+-\s+\d+)?$')

VIDEO_EXTS = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.ts', '.m2ts'}
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp'}
SUBTITLE_EXTS = {'.srt', '.ass', '.ssa', '.vtt', '.sub', '.idx', '.sup', '.smi'}
REF_RE = re.compile(r'([A-Za-z]+-[0-9]+)', re.IGNORECASE)

# ── Defaults ───────────────────────────────────────────────────────────────────

DEFAULT_VTM_EXE = r"C:\Program Files\Video Thumbnails Maker\VideoThumbnailsMaker.exe"

def _default_vtm_preset_dir() -> str:
    appdata = os.environ.get('APPDATA', '')
    if appdata:
        return os.path.join(appdata, 'Video Thumbnails Maker', 'Options')
    return os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming',
                        'Video Thumbnails Maker', 'Options')

def default_vtm_preset() -> str:
    d = _default_vtm_preset_dir()
    try:
        if os.path.isdir(d):
            for entry in sorted(os.scandir(d), key=lambda e: e.name.lower()):
                if entry.is_file() and entry.name.lower().endswith('.vtm'):
                    return entry.path
    except OSError:
        pass
    return os.path.join(d, 'Video Thumbnails Maker Preset 21 to 9.vtm')

def list_vtm_presets() -> List[str]:
    d = _default_vtm_preset_dir()
    presets: List[str] = []
    try:
        if os.path.isdir(d):
            for entry in os.scandir(d):
                if entry.is_file() and entry.name.lower().endswith('.vtm'):
                    presets.append(entry.path)
    except OSError:
        pass
    return sorted(presets, key=lambda p: os.path.basename(p).lower())

def _default_losslesscut_exe() -> str:
    candidates = [
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'LosslessCut', 'LosslessCut.exe'),
        r"C:\Program Files\LosslessCut\LosslessCut.exe",
        r"C:\Program Files\LosslessCut-win\LosslessCut.exe",
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return candidates[0] if candidates else ''

DEFAULT_LOSSLESSCUT_EXE = _default_losslesscut_exe()

# ── Low-level helpers ──────────────────────────────────────────────────────────

def _is_hidden(path: str) -> bool:
    name = os.path.basename(os.path.abspath(path))
    if platform.system() == 'Windows':
        try:
            import ctypes
            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
            if attrs != -1:
                return bool(attrs & 2)
        except Exception:
            pass
    return name.startswith('.')

def _file_size_kb(path: str) -> float:
    try:
        return os.path.getsize(path) / 1024
    except OSError:
        return 0.0

def _scan_videos(folder_path: str) -> List[dict]:
    videos: List[dict] = []
    try:
        with os.scandir(folder_path) as it:
            for entry in it:
                if entry.is_file() and not _is_hidden(entry.path):
                    _, ext = os.path.splitext(entry.name.lower())
                    if ext in VIDEO_EXTS:
                        videos.append({'name': entry.name, 'path': entry.path})
    except OSError:
        pass
    return sorted(videos, key=lambda v: v['name'].lower())


def _scan_images(folder_path: str) -> List[str]:
    images: List[str] = []
    try:
        with os.scandir(folder_path) as it:
            for entry in it:
                if entry.is_file() and not _is_hidden(entry.path):
                    _, ext = os.path.splitext(entry.name.lower())
                    if ext in IMAGE_EXTS or entry.name.lower().endswith('.jpg.jpg'):
                        images.append(entry.name)
    except OSError:
        pass
    return sorted(images, key=str.lower)


def _infer_reference_number(folder_path: str) -> str:
    cover_candidates: List[str] = []
    candidates: List[str] = []
    try:
        with os.scandir(folder_path) as it:
            for entry in it:
                if not entry.is_file() or _is_hidden(entry.path):
                    continue
                lower_name = entry.name.lower()
                match = REF_RE.search(entry.name)
                if not match:
                    continue
                ref_value = match.group(1).upper()
                if 'cover' in lower_name:
                    cover_candidates.append(ref_value)
                candidates.append(ref_value)
    except OSError:
        return ''
    if cover_candidates:
        return sorted(cover_candidates)[0]
    if not candidates:
        return ''
    counts = {value: candidates.count(value) for value in set(candidates)}
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _rename_generated_thumbnail_files(folder_path: str, generated_names: List[str], reference_number: str) -> int:
    if not reference_number or not generated_names:
        return 0

    renamed = 0
    target_index = 1
    for name in sorted(generated_names, key=str.lower):
        src = os.path.join(folder_path, name)
        if not os.path.exists(src):
            continue

        lower_name = name.lower()
        if lower_name.endswith('.jpg.jpg'):
            ext = '.jpg'
        else:
            _, ext = os.path.splitext(name)
            ext = ext.lower()

        while True:
            suffix = '' if target_index == 1 else f' {target_index}'
            target_name = f'{reference_number} Thumbnails{suffix}{ext}'
            dst = os.path.join(folder_path, target_name)
            target_index += 1
            if os.path.normcase(src) == os.path.normcase(dst):
                break
            if not os.path.exists(dst):
                os.rename(src, dst)
                renamed += 1
                break
    return renamed

# ── Data models ────────────────────────────────────────────────────────────────

@dataclass
class FolderInfo:
    full_path: str
    date: str
    video_name: str
    actor_name: str
    reference_number: str
    raw_actor_name: str = ''
    videos: List[dict] = field(default_factory=list)

    @property
    def number_of_videos(self) -> int:
        return len(self.videos)

    def to_row(self) -> dict:
        return {
            'full_path': self.full_path,
            'date': self.date,
            'video_name': self.video_name,
            'actor_name': self.actor_name,
            'raw_actor_name': self.raw_actor_name or self.actor_name,
            'reference_number': self.reference_number,
            'number_of_videos': self.number_of_videos,
            'videos': self.videos,
        }

@dataclass
class MoverInfo:
    full_path: str
    folder_name: str
    detected_actor: str
    target_dir: str
    target_exists: bool
    detected_video_name: str = ''   # base video name extracted from first video filename
    has_cover: bool = False
    has_thumbnails: bool = False
    has_subtitles: bool = False
    videos: List[dict] = field(default_factory=list)

    @property
    def number_of_videos(self) -> int:
        return len(self.videos)

    def to_row(self) -> dict:
        return {
            'full_path': self.full_path,
            'folder_name': self.folder_name,
            'detected_actor': self.detected_actor,
            'detected_video_name': self.detected_video_name,
            'has_cover': self.has_cover,
            'has_thumbnails': self.has_thumbnails,
            'has_subtitles': self.has_subtitles,
            'target_dir': self.target_dir,
            'target_exists': self.target_exists,
            'number_of_videos': self.number_of_videos,
            'videos': self.videos,
        }

# ── Renamer ────────────────────────────────────────────────────────────────────

def load_renamer_folders(
    directory: str,
    progress_callback: Optional[ScanProgressCallback] = None,
) -> List[FolderInfo]:
    """Scan directory for folders matching the strict JAV naming pattern."""
    folders: List[FolderInfo] = []
    try:
        with os.scandir(directory) as it:
            entries = [entry for entry in it if entry.is_dir() and not _is_hidden(entry.path)]

        total = len(entries)
        scanned = 0
        discovered = 0
        _emit_scan_progress(
            progress_callback,
            kind='renamer',
            phase='start',
            scanned=scanned,
            total=total,
            discovered=discovered,
            force=True,
        )

        for entry in entries:
            scanned += 1
            m = RENAMER_RE.match(entry.name)
            if m:
                date, video_name, actor_name, ref = m.groups()
                folders.append(FolderInfo(
                    full_path=entry.path,
                    date=date,
                    video_name=video_name,
                    actor_name=actor_name,
                    reference_number=ref,
                    raw_actor_name=actor_name,
                    videos=_scan_videos(entry.path),
                ))
                discovered += 1
            _emit_scan_progress(
                progress_callback,
                kind='renamer',
                phase='progress',
                scanned=scanned,
                total=total,
                discovered=discovered,
            )
    except OSError:
        pass
    _emit_scan_progress(
        progress_callback,
        kind='renamer',
        phase='complete',
        scanned=scanned if 'scanned' in locals() else 0,
        total=total if 'total' in locals() else 0,
        discovered=len(folders),
        force=True,
    )
    return sorted(folders, key=lambda f: f.date, reverse=True)


def build_file_rename_preview(info: FolderInfo, *, include_videos: bool = True) -> List[dict]:
    """Return planned file renames for a folder using the same rules as the actual rename flow."""
    folder_path = info.full_path
    if not os.path.isdir(folder_path):
        return []

    try:
        with os.scandir(folder_path) as it:
            files = [e for e in it if e.is_file() and not _is_hidden(e.path)]
    except OSError:
        return []

    preview: List[dict] = []
    webp_files = sorted(f.name for f in files if f.name.lower().endswith('.webp'))
    jpg_entries = [f for f in files if f.name.lower().endswith('.jpg')]
    video_files = sorted(
        f.name for f in files
        if os.path.splitext(f.name.lower())[1] in {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm'}
    )
    large_jpgs = sorted(f.name for f in jpg_entries if _file_size_kb(f.path) > 700)
    small_jpgs = sorted(f.name for f in jpg_entries if _file_size_kb(f.path) <= 700)

    def _append(old_name: str, new_name: str, kind: str) -> None:
        if os.path.normcase(old_name) != os.path.normcase(new_name):
            preview.append({
                'old_name': old_name,
                'new_name': new_name,
                'kind': kind,
            })

    for i, name in enumerate(webp_files):
        idx = f' {i + 1}' if len(webp_files) > 1 else ''
        _append(name, f'{info.reference_number} Thumbnails{idx}.webp', 'thumbnail')

    for i, name in enumerate(large_jpgs):
        idx = f' {i + 1}' if len(large_jpgs) > 1 else ''
        _append(name, f'{info.reference_number} Thumbnails{idx}.jpg', 'thumbnail')

    for i, name in enumerate(small_jpgs):
        idx = f' {i + 1}' if len(small_jpgs) > 1 else ''
        _append(name, f'{info.reference_number} Cover{idx}.jpg', 'cover')

    if include_videos:
        for i, name in enumerate(video_files):
            _, ext = os.path.splitext(name)
            idx = f' - {i + 1}' if len(video_files) > 1 else ''
            _append(name, f'{info.actor_name} - {info.video_name}{idx}{ext}', 'video')

    return preview


def rename_folder(info: FolderInfo) -> dict:
    """
    Rename all files inside a folder then rename the folder itself.
    Returns {'success': bool, 'message': str, 'new_path': str}.
    """
    folder_path = info.full_path
    if not os.path.isdir(folder_path):
        return {'success': False, 'message': f'Not found: {folder_path}', 'new_path': folder_path}

    errors: List[str] = []

    preview = build_file_rename_preview(info, include_videos=True)

    def _safe_rename(old: str, new: str) -> None:
        src = os.path.join(folder_path, old)
        dst = os.path.join(folder_path, new)
        if os.path.normcase(src) != os.path.normcase(dst):
            try:
                os.rename(src, dst)
            except OSError as e:
                errors.append(f'{old} → {new}: {e}')

    for item in preview:
        _safe_rename(item['old_name'], item['new_name'])

    # Rename the folder last
    parent = os.path.dirname(folder_path)
    base_new = f'{info.date} - {info.video_name}'
    candidate = os.path.join(parent, base_new)
    norm_orig = os.path.normcase(os.path.abspath(folder_path))
    final_path = folder_path

    if os.path.normcase(os.path.abspath(candidate)) != norm_orig:
        n = 1
        while os.path.exists(candidate) and os.path.normcase(os.path.abspath(candidate)) != norm_orig:
            candidate = os.path.join(parent, f'{base_new} ({n})')
            n += 1
            if n > 100:
                errors.append(f'Could not find a unique name for {base_new}')
                candidate = None
                break
        if candidate:
            try:
                os.rename(folder_path, candidate)
                final_path = candidate
            except OSError as e:
                errors.append(f'Folder rename failed: {e}')

    if errors:
        return {'success': False, 'message': '; '.join(errors), 'new_path': final_path}
    return {'success': True, 'message': 'OK', 'new_path': final_path}


def rename_folders_batch(folder_infos: List[FolderInfo]) -> dict:
    ok, failed = 0, []
    for info in folder_infos:
        r = rename_folder(info)
        if r['success']:
            ok += 1
        else:
            failed.append(f'{os.path.basename(info.full_path)}: {r["message"]}')
    if not failed:
        return {'success': True, 'message': f'Renamed {ok} folder(s) successfully.'}
    return {
        'success': False,
        'message': f'Renamed {ok}, failed {len(failed)}:\n' + '\n'.join(failed),
    }

# ── Folder Mover ───────────────────────────────────────────────────────────────

def _find_first_video(folder_path: str) -> Optional[str]:
    try:
        with os.scandir(folder_path) as it:
            for entry in it:
                if entry.is_file() and not _is_hidden(entry.path):
                    _, ext = os.path.splitext(entry.name.lower())
                    if ext in VIDEO_EXTS:
                        return entry.path
    except OSError:
        pass
    return None

def _extract_actor(filename: str) -> Optional[str]:
    base = os.path.splitext(os.path.basename(filename))[0]
    m = ACTOR_VIDEO_RE.match(base)
    return m.group('Actor').strip() if m else None


def _extract_video_name(filename: str) -> Optional[str]:
    """Extract the base video name portion from 'Actor - Video Name[- index].ext'."""
    base = os.path.splitext(os.path.basename(filename))[0]
    m = ACTOR_VIDEO_RE.match(base)
    return m.group('Video').strip() if m else None


def _extract_folder_mover_metadata(folder_name: str) -> Tuple[str, str]:
    """Extract (actor_name, video_name) from a strict pre-renamer folder name."""
    match = RENAMER_RE.match(folder_name)
    if not match:
        return '', ''
    _, video_name, actor_name, _ = match.groups()
    return actor_name.strip(), video_name.strip()

def _resolve_actor_dir(base_dir: str, actor: str) -> Tuple[str, bool]:
    """Return (target_path, exists). Checks base_dir first, then its parent."""
    candidate = os.path.join(base_dir, actor)
    if os.path.isdir(candidate):
        return candidate, True
    parent = os.path.dirname(base_dir)
    if parent and parent != base_dir:
        p = os.path.join(parent, actor)
        if os.path.isdir(p):
            return p, True
    return candidate, False


def _resolve_actor_dir_explicit(target_base: str, actor: str) -> Tuple[str, bool]:
    """Return (target_path, exists) using a user-specified target base directory."""
    candidate = os.path.join(target_base, actor)
    return candidate, os.path.isdir(candidate)


def _scan_mover_assets(folder_path: str) -> Tuple[bool, bool, bool]:
    """Return (has_cover, has_thumbnails, has_subtitles) for a mover folder."""
    cover = False
    thumbs = False
    subtitles = False
    try:
        with os.scandir(folder_path) as it:
            for entry in it:
                if not entry.is_file() or _is_hidden(entry.path):
                    continue
                lower = entry.name.lower()
                _, ext = os.path.splitext(lower)
                if ext in SUBTITLE_EXTS:
                    subtitles = True
                if ext in IMAGE_EXTS or lower.endswith('.jpg.jpg'):
                    if 'thumbnail' in lower:
                        thumbs = True
                    if 'cover' in lower:
                        cover = True
                if cover and thumbs and subtitles:
                    break
    except OSError:
        pass
    return cover, thumbs, subtitles


def load_mover_folders(
    directory: str,
    target_base: str = '',
    progress_callback: Optional[ScanProgressCallback] = None,
) -> List[MoverInfo]:
    """Scan directory for date-prefixed folders and suggest actor subdirectory targets.

    target_base: if set, actor folders are resolved relative to this directory
                 instead of auto-detecting from the scanned directory / its parent.
    """
    results: List[MoverInfo] = []
    use_explicit = bool(target_base and os.path.isdir(target_base))
    try:
        with os.scandir(directory) as it:
            entries = [entry for entry in it if entry.is_dir() and not _is_hidden(entry.path)]

        total = len(entries)
        scanned = 0
        discovered = 0
        _emit_scan_progress(
            progress_callback,
            kind='mover',
            phase='start',
            scanned=scanned,
            total=total,
            discovered=discovered,
            force=True,
        )

        for entry in entries:
            scanned += 1
            if not MOVER_RE.match(entry.name) or RENAMER_RE.match(entry.name):
                _emit_scan_progress(
                    progress_callback,
                    kind='mover',
                    phase='progress',
                    scanned=scanned,
                    total=total,
                    discovered=discovered,
                )
                continue
            videos = _scan_videos(entry.path)
            folder_actor, folder_video_name = _extract_folder_mover_metadata(entry.name)
            if not videos and not folder_actor:
                _emit_scan_progress(
                    progress_callback,
                    kind='mover',
                    phase='progress',
                    scanned=scanned,
                    total=total,
                    discovered=discovered,
                )
                continue
            first_video = videos[0]['path'] if videos else None
            actor = _extract_actor(first_video) if first_video else ''
            video_name = _extract_video_name(first_video) if first_video else ''
            if not actor:
                actor = folder_actor
            if not video_name:
                video_name = folder_video_name
            has_cover, thumb_state, has_subtitles = _scan_mover_assets(entry.path)
            if actor:
                if use_explicit:
                    target, exists = _resolve_actor_dir_explicit(target_base, actor)
                else:
                    target, exists = _resolve_actor_dir(directory, actor)
            else:
                target, exists = '', False
            results.append(MoverInfo(
                full_path=entry.path,
                folder_name=entry.name,
                detected_actor=actor or '',
                target_dir=target,
                target_exists=exists,
                detected_video_name=video_name or '',
                has_cover=has_cover,
                has_thumbnails=thumb_state,
                has_subtitles=has_subtitles,
                videos=videos,
            ))
            discovered += 1
            _emit_scan_progress(
                progress_callback,
                kind='mover',
                phase='progress',
                scanned=scanned,
                total=total,
                discovered=discovered,
            )
    except OSError:
        pass
    _emit_scan_progress(
        progress_callback,
        kind='mover',
        phase='complete',
        scanned=scanned if 'scanned' in locals() else 0,
        total=total if 'total' in locals() else 0,
        discovered=len(results),
        force=True,
    )
    return sorted(results, key=lambda f: f.folder_name.lower())


def recalc_target(directory: str, actor: str, target_base: str = '') -> Tuple[str, bool]:
    """Recompute target dir when actor name is edited in the UI."""
    if not actor.strip():
        return '', False
    if target_base and os.path.isdir(target_base):
        return _resolve_actor_dir_explicit(target_base, actor.strip())
    return _resolve_actor_dir(directory, actor.strip())


def move_folder(source_path: str, target_dir: str) -> dict:
    if not os.path.isdir(source_path):
        return {'success': False, 'message': f'Source not found: {source_path}'}
    if not os.path.isdir(target_dir):
        try:
            os.makedirs(target_dir)
        except OSError as e:
            return {'success': False, 'message': f'Cannot create target dir: {e}'}
    try:
        shutil.move(source_path, target_dir)
        return {
            'success': True,
            'message': f"Moved '{os.path.basename(source_path)}' → '{os.path.basename(target_dir)}'",
        }
    except (shutil.Error, OSError) as e:
        return {'success': False, 'message': str(e)}

# ── Mover extras ───────────────────────────────────────────────────────────────

def rename_videos_for_actor(folder_path: str, new_actor: str, video_name: str) -> dict:
    """Rename video files inside folder_path to match a new actor name.

    Renames 'OldActor - VideoName.ext' → 'NewActor - VideoName.ext'.
    Skips files whose names are already correct (case-insensitive).
    Returns {'success': bool, 'message': str, 'renamed': int}.
    """
    if not os.path.isdir(folder_path):
        return {'success': False, 'message': f'Folder not found: {folder_path}', 'renamed': 0}
    if not new_actor or not video_name:
        return {'success': False, 'message': 'Actor name and video name are required.', 'renamed': 0}

    errors: List[str] = []
    renamed = 0
    try:
        with os.scandir(folder_path) as it:
            video_files = sorted(
                [e for e in it if e.is_file() and not _is_hidden(e.path)
                 and os.path.splitext(e.name.lower())[1] in VIDEO_EXTS],
                key=lambda e: e.name.lower(),
            )
    except OSError as exc:
        return {'success': False, 'message': str(exc), 'renamed': 0}

    for i, entry in enumerate(video_files):
        _, ext = os.path.splitext(entry.name)
        idx = f' - {i + 1}' if len(video_files) > 1 else ''
        new_name = f'{new_actor} - {video_name}{idx}{ext}'
        new_path = os.path.join(folder_path, new_name)
        if os.path.normcase(entry.path) != os.path.normcase(new_path):
            try:
                os.rename(entry.path, new_path)
                renamed += 1
            except OSError as e:
                errors.append(f'{entry.name} → {new_name}: {e}')

    if errors:
        return {'success': False, 'message': '; '.join(errors), 'renamed': renamed}
    return {'success': True, 'message': f'Renamed {renamed} video(s).', 'renamed': renamed}


def check_move_conflicts(moves: List[dict]) -> List[dict]:
    """Check a list of proposed moves for folder-name collisions at the destination.

    Each item in moves: {'source_path': str, 'target_dir': str}.
    Returns a parallel list where each entry has:
      'status': 'clear' | 'conflict' | 'error'
      'conflicts': list of file-level conflict dicts (only when status=='conflict')
    """
    results: List[dict] = []
    for move in moves:
        source_path = move.get('source_path', '')
        target_dir  = move.get('target_dir', '')
        folder_name = os.path.basename(source_path)

        if not source_path or not target_dir:
            results.append({'source_path': source_path, 'folder_name': folder_name,
                            'status': 'error', 'message': 'Missing paths.'})
            continue
        if not os.path.isdir(source_path):
            results.append({'source_path': source_path, 'folder_name': folder_name,
                            'status': 'error', 'message': 'Source folder not found.'})
            continue

        final_path = os.path.join(target_dir, folder_name)
        if not os.path.exists(final_path):
            results.append({'source_path': source_path, 'target_dir': target_dir,
                            'folder_name': folder_name, 'status': 'clear'})
            continue

        # Destination folder already exists — enumerate file-level conflicts
        conflicts: List[dict] = []
        try:
            for entry in os.scandir(source_path):
                if entry.is_file():
                    dest_file = os.path.join(final_path, entry.name)
                    if os.path.exists(dest_file):
                        _, ext = os.path.splitext(entry.name.lower())
                        src_size = os.path.getsize(entry.path)
                        dst_size = os.path.getsize(dest_file)
                        conflicts.append({
                            'filename': entry.name,
                            'is_video': ext in VIDEO_EXTS,
                            'source_size': src_size,
                            'target_size': dst_size,
                            'identical_size': src_size == dst_size,
                        })
        except OSError as e:
            results.append({'source_path': source_path, 'folder_name': folder_name,
                            'status': 'error', 'message': f'Cannot read source: {e}'})
            continue

        results.append({'source_path': source_path, 'target_dir': target_dir,
                        'folder_name': folder_name, 'final_path': final_path,
                        'status': 'conflict', 'conflicts': conflicts})

    return results


def merge_folder(source_path: str, target_dir_path: str,
                 rename_video_to: Optional[str] = None) -> dict:
    """Merge all files from source_path into an existing target_dir_path.

    If rename_video_to is provided, the first video file is renamed before merging.
    Non-unique files at the destination are overwritten.
    The source folder is removed after all files are moved.
    Returns {'success': bool, 'message': str}.
    """
    if not os.path.isdir(source_path):
        return {'success': False, 'message': f'Source not found: {source_path}'}
    if not os.path.isdir(target_dir_path):
        return {'success': False, 'message': f'Target not found: {target_dir_path}'}

    if rename_video_to:
        try:
            with os.scandir(source_path) as it:
                for entry in it:
                    if entry.is_file():
                        _, ext = os.path.splitext(entry.name.lower())
                        if ext in VIDEO_EXTS:
                            new_name = (rename_video_to
                                        if rename_video_to.lower().endswith(ext)
                                        else f'{rename_video_to}{ext}')
                            os.rename(entry.path, os.path.join(source_path, new_name))
                            break
        except OSError as e:
            return {'success': False, 'message': f'Cannot rename video before merge: {e}'}

    errors: List[str] = []
    try:
        with os.scandir(source_path) as it:
            entries = list(it)
        for entry in entries:
            dest = os.path.join(target_dir_path, entry.name)
            try:
                if entry.is_file():
                    if os.path.exists(dest):
                        os.remove(dest)
                    shutil.move(entry.path, dest)
                elif entry.is_dir():
                    if not os.path.exists(dest):
                        shutil.move(entry.path, dest)
                    else:
                        errors.append(f'Subdirectory conflict: {entry.name}')
            except OSError as e:
                errors.append(f'{entry.name}: {e}')
    except OSError as e:
        return {'success': False, 'message': f'Cannot read source: {e}'}

    if errors:
        return {'success': False, 'message': '; '.join(errors)}

    try:
        os.rmdir(source_path)
    except OSError as e:
        return {'success': False,
                'message': f'Files moved but source folder removal failed: {e}'}

    return {'success': True,
            'message': f"Merged '{os.path.basename(source_path)}' → '{os.path.basename(target_dir_path)}'"}


# ── Image listing ──────────────────────────────────────────────────────────────

def list_folder_images(folder_path: str) -> List[dict]:
    """Return previewable images sorted: covers first, then by size desc."""
    images: List[dict] = []
    try:
        with os.scandir(folder_path) as it:
            for entry in it:
                if not entry.is_file() or _is_hidden(entry.path):
                    continue
                lower = entry.name.lower()
                _, ext = os.path.splitext(lower)
                if ext not in IMAGE_EXTS:
                    continue
                try:
                    size = os.path.getsize(entry.path)
                except OSError:
                    size = 0
                images.append({
                    'name': entry.name,
                    'path': entry.path,
                    'size': size,
                    'is_cover': 'cover' in lower,
                })
    except OSError:
        pass
    images.sort(key=lambda x: (0 if x['is_cover'] else 1, -x['size'], x['name'].lower()))
    return images


def has_thumbnails(folder_path: str) -> bool:
    """Return True if the folder contains at least one image that looks like thumbnails."""
    try:
        with os.scandir(folder_path) as it:
            for entry in it:
                if not entry.is_file() or _is_hidden(entry.path):
                    continue
                lower = entry.name.lower()
                _, ext = os.path.splitext(lower)
                if ext in IMAGE_EXTS and 'thumbnail' in lower:
                    return True
    except OSError:
        pass
    return False


def has_cover_only(folder_path: str) -> bool:
    """Return True if folder has cover image(s) but no thumbnail images.

    'Cover only' = at least one image with 'cover' in the filename,
    and no .webp files, and no other image files (nothing that looks
    like a thumbnail strip).
    """
    has_cover = False
    has_thumbs = False
    try:
        with os.scandir(folder_path) as it:
            for entry in it:
                if not entry.is_file() or _is_hidden(entry.path):
                    continue
                lower = entry.name.lower()
                _, ext = os.path.splitext(lower)
                if ext in IMAGE_EXTS:
                    if 'cover' in lower:
                        has_cover = True
                    else:
                        has_thumbs = True
    except OSError:
        pass
    return has_cover and not has_thumbs


def has_vtm_cover_screenshot(folder_path: str) -> bool:
    """Return True if folder contains a .jpg.jpg file.

    When VTM processes a folder that has no video (only a cover image),
    it generates a thumbnail of the cover itself, naming it
    '{original_name}.jpg' — producing a double extension like
    '{REF} Cover.jpg.jpg'.  This signals VTM has run but only found
    the cover to work with (real video thumbnails are absent).
    """
    try:
        with os.scandir(folder_path) as it:
            for entry in it:
                if entry.is_file() and entry.name.lower().endswith('.jpg.jpg'):
                    return True
    except OSError:
        pass
    return False


def list_all_folder_files(folder_path: str) -> List[dict]:
    """Return ALL non-hidden files in a folder.
    Sort order: images (covers first, then by size desc), then videos (by size desc), then others."""
    files: List[dict] = []
    try:
        with os.scandir(folder_path) as it:
            for entry in it:
                if not entry.is_file() or _is_hidden(entry.path):
                    continue
                try:
                    size = entry.stat().st_size
                except OSError:
                    size = 0
                lower = entry.name.lower()
                _, ext = os.path.splitext(lower)
                is_image = ext in IMAGE_EXTS
                is_video = ext in VIDEO_EXTS
                is_subtitle = ext in SUBTITLE_EXTS
                files.append({
                    'name': entry.name,
                    'path': entry.path,
                    'size': size,
                    'ext': ext,
                    'is_image': is_image,
                    'is_video': is_video,
                    'is_subtitle': is_subtitle,
                    'is_cover': is_image and 'cover' in lower,
                })
    except OSError:
        pass

    def _sort_key(f: dict):
        if f['is_image']:
            return (0, 0 if f['is_cover'] else 1, -f['size'], f['name'].lower())
        if f['is_video']:
            return (1, 0, -f['size'], f['name'].lower())
        return (2, 0, 0, f['name'].lower())

    files.sort(key=_sort_key)
    return files


def cleanup_folder_files(
    folder_path: str,
    *,
    delete_other_files: bool = True,
    delete_small_videos: bool = False,
    min_video_mb: float = 30.0,
) -> dict:
    """Delete unwanted files from a folder based on organiser cleanup rules."""
    files = list_all_folder_files(folder_path)
    if not files:
        return {'success': True, 'deleted_count': 0, 'message': 'Nothing to clean.'}

    min_video_bytes = max(0.0, float(min_video_mb or 0)) * 1024 * 1024
    delete_paths: List[str] = []

    for info in files:
        is_media = info['is_video'] or info['is_image'] or info.get('is_subtitle', False)
        if delete_other_files and not is_media:
            delete_paths.append(info['path'])
            continue
        if delete_small_videos and info['is_video'] and info['size'] < min_video_bytes:
            delete_paths.append(info['path'])

    if not delete_paths:
        return {'success': True, 'deleted_count': 0, 'message': 'No files matched the cleanup rules.'}

    deleted = 0
    errors: List[str] = []
    for path in delete_paths:
        try:
            os.remove(path)
            deleted += 1
        except OSError as exc:
            errors.append(f'{os.path.basename(path)}: {exc}')

    if errors:
        return {
            'success': False,
            'deleted_count': deleted,
            'message': f'Deleted {deleted} file(s), failed {len(errors)}: ' + '; '.join(errors),
        }
    return {
        'success': True,
        'deleted_count': deleted,
        'message': f'Deleted {deleted} file(s).',
    }


def rename_file(old_path: str, new_name: str) -> dict:
    """Rename a file within its current folder.
    Returns {'success': bool, 'message': str, 'new_path': str}."""
    if not os.path.isfile(old_path):
        return {'success': False, 'message': f'File not found: {old_path}', 'new_path': ''}
    new_name = new_name.strip()
    if not new_name:
        return {'success': False, 'message': 'New name cannot be empty', 'new_path': ''}
    folder = os.path.dirname(old_path)
    new_path = os.path.join(folder, new_name)
    if os.path.normcase(new_path) != os.path.normcase(old_path) and os.path.exists(new_path):
        return {'success': False, 'message': f'Already exists: {new_name}', 'new_path': ''}
    try:
        os.rename(old_path, new_path)
        return {'success': True, 'message': f'Renamed to {new_name}', 'new_path': new_path}
    except OSError as e:
        return {'success': False, 'message': str(e), 'new_path': ''}


def delete_file(path: str) -> dict:
    """Delete any file. Returns {'success': bool, 'message': str}."""
    if not os.path.isfile(path):
        return {'success': False, 'message': f'File not found: {path}'}
    try:
        os.remove(path)
        return {'success': True, 'message': f'Deleted {os.path.basename(path)}'}
    except OSError as e:
        return {'success': False, 'message': str(e)}


# ── Image file operations ──────────────────────────────────────────────────────

def delete_image_file(path: str) -> dict:
    """Delete a single image file. Returns {'success': bool, 'message': str}."""
    if not os.path.isfile(path):
        return {'success': False, 'message': f'File not found: {path}'}
    _, ext = os.path.splitext(path.lower())
    if ext not in IMAGE_EXTS:
        return {'success': False, 'message': f'Not an image file: {path}'}
    try:
        os.remove(path)
        return {'success': True, 'message': f'Deleted {os.path.basename(path)}'}
    except OSError as e:
        return {'success': False, 'message': str(e)}


def rename_images_in_folder(info: FolderInfo) -> dict:
    """Rename only image files inside a folder (no video renaming, no folder rename).

    Uses the same rules as rename_folder:
      WebP             → {REF} Thumbnails[N].webp
      Large JPG >700KB → {REF} Thumbnails[N].jpg
      Small JPG ≤700KB → {REF} Cover[N].jpg
    Returns {'success': bool, 'message': str}.
    """
    folder_path = info.full_path
    if not os.path.isdir(folder_path):
        return {'success': False, 'message': f'Not found: {folder_path}'}

    errors: List[str] = []
    preview = build_file_rename_preview(info, include_videos=False)

    def _safe_rename(old: str, new: str) -> None:
        src = os.path.join(folder_path, old)
        dst = os.path.join(folder_path, new)
        if os.path.normcase(src) != os.path.normcase(dst):
            try:
                os.rename(src, dst)
            except OSError as e:
                errors.append(f'{old} → {new}: {e}')

    for item in preview:
        _safe_rename(item['old_name'], item['new_name'])

    if errors:
        return {'success': False, 'message': '; '.join(errors)}
    total = len(preview)
    return {'success': True, 'message': f'Renamed {total} image(s).'}


# ── VTM thumbnail generation ───────────────────────────────────────────────────

def generate_thumbnails(folder_path: str, vtm_exe: str, vtm_preset: str,
                        timeout: int = 300) -> dict:
    if not os.path.isdir(folder_path):
        return {'success': False, 'message': f'Not a directory: {folder_path}'}
    if not os.path.isfile(vtm_exe):
        return {'success': False, 'message': f'VTM not found: {vtm_exe}'}
    if not os.path.isfile(vtm_preset):
        return {'success': False, 'message': f'VTM preset not found: {vtm_preset}'}
    timeout = max(30, min(1800, int(timeout)))
    before_images = set(_scan_images(folder_path))
    try:
        result = subprocess.run(
            [vtm_exe, vtm_preset, folder_path.rstrip('\\'), '/silent'],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode == 0:
            after_images = set(_scan_images(folder_path))
            generated_names = sorted(after_images - before_images, key=str.lower)
            reference_number = _infer_reference_number(folder_path)
            renamed_count = _rename_generated_thumbnail_files(folder_path, generated_names, reference_number)

            message = f"Thumbnails generated for {os.path.basename(folder_path)}"
            if renamed_count:
                message += f"; used ref {reference_number}; renamed {renamed_count} image(s) to {reference_number} Thumbnails"
            elif generated_names and not reference_number:
                message += '; no reference found, so generated images kept their VTM names'
            return {'success': True, 'message': message}
        err = result.stderr or result.stdout or f'exit code {result.returncode}'
        return {'success': False, 'message': f'VTM failed: {err[:400]}'}
    except subprocess.TimeoutExpired:
        return {'success': False, 'message': 'VTM timed out'}
    except Exception as e:
        return {'success': False, 'message': str(e)}

# ── External tool launchers ────────────────────────────────────────────────────

def open_path(path: str) -> None:
    """Open a file or folder with the OS default handler."""
    if platform.system() == 'Windows':
        os.startfile(path)
    elif platform.system() == 'Darwin':
        subprocess.Popen(['open', path])
    else:
        subprocess.Popen(['xdg-open', path])


def open_in_losslesscut(video_path: str, losslesscut_exe: str) -> dict:
    if not losslesscut_exe or not os.path.isfile(losslesscut_exe):
        return {'success': False, 'message': f'LosslessCut not found: {losslesscut_exe}'}
    if not os.path.isfile(video_path):
        return {'success': False, 'message': f'Video not found: {video_path}'}
    try:
        subprocess.Popen([losslesscut_exe, video_path])
        return {'success': True, 'message': 'Launched LosslessCut'}
    except Exception as e:
        return {'success': False, 'message': str(e)}


def open_folder_in_explorer(folder_path: str) -> None:
    if platform.system() == 'Windows':
        subprocess.Popen(['explorer', os.path.normpath(folder_path)])
    else:
        open_path(folder_path)
